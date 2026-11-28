// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `scan` binds a Python reply to the snapshot before the model reads it (AD-450). Each
// planted difference between the reply and the files refuses the reply.

use std::fs;

use archkeel_facts::envelope::{Profile, Reply};
use archkeel_snapshot::test_tree::Tree;
use serde_json::json;

use super::*;

/// The canonical root of a tree, as the composition requires it.
fn root(tree: &Tree) -> Root {
    let path = fs::canonicalize(&tree.root).unwrap();
    Root::of(path.to_str().unwrap()).unwrap()
}

fn reply(tree: &Tree) -> Reply {
    let request = json!({
        "protocol_version": "10.0.0",
        "snapshot": {"root": tree.path(), "git_head": "a".repeat(40), "dirty": false},
        "scope": {"roots": ["src"], "namespace": "app", "exclude_test_sources": false},
        "resolver": resolver(),
    });
    crate::run::reply_of(Profile::Python, request.to_string().as_bytes()).unwrap()
}

fn project() -> Tree {
    Tree::new(&[
        (
            "pyproject.toml",
            "[project]\nrequires-python = \">=3.11\"\n",
        ),
        ("src/app/__init__.py", ""),
        (
            "src/app/client.py",
            "import app.service\nimport requests\nimport os\n",
        ),
        ("src/app/service.py", "VALUE = 1\n"),
    ])
}

#[test]
fn direct_calls_need_the_live_links_to_the_caller_and_provider() {
    let tree = Tree::new(&[
        ("src/app/__init__.py", ""),
        ("src/app/service.py", "def sink():\n    return 1\n"),
        (
            "src/app/client.py",
            "from app.service import sink\n\ndef run():\n    return sink()\n",
        ),
    ]);
    let original = reply(&tree);
    let witnesses = original.facts.direct_calls.as_ref().unwrap();
    assert_eq!(witnesses.len(), 1);
    assert!(archkeel_store::ingest_typed(original.clone()).is_ok());

    let mut forged = original.clone();
    forged.facts.direct_calls.as_mut().unwrap()[0].2 = None;
    assert_eq!(
        archkeel_store::ingest_typed(forged).err().as_deref(),
        Some("invalid live direct-call witness")
    );

    let archived = serde_json::to_vec(&original).unwrap();
    let decoded: Reply = serde_json::from_slice(&archived).unwrap();
    assert!(decoded.facts.direct_calls.is_none());
}

#[test]
fn the_request_leaves_the_target_to_the_collector() {
    let request = resolver();
    assert_eq!(request, json!({"language": "python", "phase": "imports"}));
}

#[test]
fn a_reply_of_the_snapshot_is_bound_to_it() {
    let tree = project();
    let root = root(&tree);
    let reply = reply(&tree);
    assert_eq!(reply.facts.runtime.version, "3.11.0");
    assert_eq!(
        reply.facts.runtime.target_source,
        Some(archkeel_facts::envelope::TargetSource::Requirement)
    );
    assert!(reply.facts.inputs.len() >= 4, "{:?}", reply.facts.inputs);
    assert_eq!(bound(&root, &reply), Ok(()));
}

#[test]
fn a_live_call_witness_is_bound_and_an_archive_has_no_call_authority() {
    use archkeel_facts::ids::FactId;
    use archkeel_store::{ingest_typed, CallOwners, Ingested};

    let tree = Tree::new(&[
        ("pyproject.toml", "[project]\nrequires-python = \">=3.11\"\n"),
        ("src/app/__init__.py", ""),
        ("src/app/service.py", "class Store:\n    def page(self):\n        return 1\n"),
        ("src/app/client.py", "from app.service import Store\n\ndef run():\n    store = Store()\n    return store.page()\n"),
    ]);
    let original = reply(&tree);
    let live = ingest_typed(original.clone()).expect("the linked witness passes the store");
    let owners = Ingested::call_owners(&live).expect("live call owners");
    let calls = CallOwners::calls(owners);
    assert_eq!(calls.len(), 1);
    let call = &calls[0];
    assert_eq!(call.scope, "app.client.run");
    assert_eq!(call.target, "app.service.Store.page");
    assert!(CallOwners::targets(owners).contains("app.service.Store.page"));

    let bytes = serde_json::to_vec(&original).unwrap();
    let archived = ingest_typed(serde_json::from_slice(&bytes).unwrap()).unwrap();
    assert!(Ingested::call_owners(&archived).is_none());

    let mut forged = original.clone();
    let row = &mut forged.facts.constructed_calls.as_mut().unwrap().calls[0];
    row.constructor = row.call.clone();
    assert!(ingest_typed(forged)
        .err()
        .unwrap()
        .contains("constructor-to-method"));

    let mut forged = original;
    forged.facts.constructed_calls.as_mut().unwrap().calls[0].binding = Some(FactId::new("other"));
    assert!(ingest_typed(forged)
        .err()
        .unwrap()
        .contains("constructor-to-method"));
}

#[test]
fn a_planted_digest_or_a_changed_file_refuses_the_reply() {
    let tree = project();
    let root = root(&tree);
    let original = reply(&tree);

    let mut fake = original.clone();
    fake.facts.inputs[0].digest = "0".repeat(64);
    assert!(bound(&root, &fake)
        .unwrap_err()
        .contains("differs from its digest"));

    let mut fake = original.clone();
    fake.facts.source.source_digest = "0".repeat(64);
    assert!(bound(&root, &fake).unwrap_err().contains("source digest"));

    let mut fake = original.clone();
    fake.facts.inputs.pop();
    assert!(bound(&root, &fake).unwrap_err().contains("source digest"));

    fs::write(tree.root.join("src/app/service.py"), "VALUE = 2\n").unwrap();
    assert!(bound(&root, &original)
        .unwrap_err()
        .contains("differs from its digest"));
    fs::remove_file(tree.root.join("src/app/service.py")).unwrap();
    assert!(bound(&root, &original)
        .unwrap_err()
        .contains("cannot be read again"));
}

/// The refusal of a changed copy of a real survey by the store or the check of the collector
/// (AD-688), or an empty text.
fn refusal(reply: Reply) -> String {
    archkeel_store::ingest_typed(reply)
        .and_then(|ingested| crate::check(&ingested.reply().facts))
        .err()
        .unwrap_or_default()
}

#[test]
fn the_store_accepts_a_complete_survey_and_refuses_each_planted_claim() {
    use archkeel_facts::envelope::{LimitSupport, Target};
    use archkeel_facts::ids::PackageName;

    let tree = project();
    let original = reply(&tree);
    assert!(
        original.facts.coverage.full_scope,
        "{:?}",
        original.facts.coverage
    );
    assert_eq!(refusal(original.clone()), "");
    let limits = original.facts.profile_limits.unwrap();
    // AD-504: the linked survey states its symbols and its routes with the feature that binds them.
    assert_eq!(limits.dependency_symbols, LimitSupport::Supported);
    assert_eq!(limits.interface_boundary, LimitSupport::Supported);
    assert!(original
        .facts
        .capabilities
        .resolution_features
        .contains(&"import-routes-v1".to_owned()));

    type Change = fn(&mut Reply);
    let cases: [(&str, Change); 9] = [
        // AD-688: the validation table of the survey registers its sets; a block cannot widen
        // the features that the store checks.
        ("not registered", |r| {
            r.facts.validation.registered.pop();
        }),
        (
            "the store does not check the resolution feature eval-v1",
            |r| {
                let set = &mut r.facts.validation.registered[0];
                set.optional_features.push("eval-v1".to_owned());
            },
        ),
        ("not registered", |r| {
            r.facts
                .capabilities
                .resolution_features
                .push("static-imports".to_owned());
        }),
        ("profile symbol statement does not match", |r| {
            r.facts.capabilities.resolution_features.clear();
        }),
        ("profile symbol statement does not match", |r| {
            if let Some(limits) = r.facts.profile_limits.as_mut() {
                limits.dependency_symbols = LimitSupport::Unsupported;
            }
        }),
        ("external target", |r| {
            let local = r
                .facts
                .imports
                .iter_mut()
                .find(|t| matches!(t, Target::Local { .. }));
            if let Some(target) = local {
                *target = Target::External {
                    import_id: target.import_id().clone(),
                    package: PackageName::new("app"),
                };
            }
        }),
        ("a builtin target must be standard", |r| {
            let found = r
                .facts
                .imports
                .iter_mut()
                .find(|t| matches!(t, Target::External { .. }));
            if let Some(target) = found {
                *target = Target::Builtin {
                    import_id: target.import_id().clone(),
                    name: "requests".to_owned(),
                };
            }
        }),
        ("an external target must be a package", |r| {
            let found = r
                .facts
                .imports
                .iter_mut()
                .find(|t| matches!(t, Target::Builtin { .. }));
            if let Some(target) = found {
                *target = Target::External {
                    import_id: target.import_id().clone(),
                    package: PackageName::new("os"),
                };
            }
        }),
        ("a Python import has no specifier", |r| {
            if let Some(archkeel_facts::Section::Imports(records)) = r.facts.sections.first_mut() {
                if let archkeel_facts::ImportFact::Import(data) = &mut records[0].data {
                    data.type_only = Some(false);
                }
            }
        }),
    ];
    for (reason, change) in cases {
        let mut changed = original.clone();
        change(&mut changed);
        let refused = refusal(changed);
        assert!(refused.contains(reason), "{reason}: {refused}");
    }
    registered_sets(&original);
}

/// The registered sets of the validation table of the survey (AD-688; AD-450, AD-518, AD-520,
/// AD-658, AD-666, AD-680, AD-682, AD-684, AD-686): the five survey sections without a construct,
/// or with the `constructs` section and `assert` `supported`, followed by the later construct kinds
/// in their order, each `supported` or `partial`; `getattr` comes with `typing_signals`.
fn registered_sets(original: &Reply) {
    use archkeel_facts::envelope::{ConstructSupport, SectionName};
    let caps = |change: &dyn Fn(&mut Reply)| {
        let mut changed = original.clone();
        change(&mut changed);
        refusal(changed)
    };
    let drop_section = |reply: &mut Reply, name: SectionName| {
        reply
            .facts
            .capabilities
            .sections
            .retain(|each| *each != name);
        reply
            .facts
            .sections
            .retain(|each| each.name() != name.as_str());
    };
    let not_registered = "source sections or resolution features are not registered";
    let constructs = &original.facts.capabilities.constructs;
    assert_eq!(constructs.len(), 12, "{constructs:?}");
    // `getattr` without `typing_signals`, and the five first kinds with it, are no set.
    assert_eq!(
        caps(&|r| drop_section(r, SectionName::TypingSignals)),
        not_registered
    );
    let renamed = |index: usize, name: &'static str| {
        move |r: &mut Reply| r.facts.capabilities.constructs[index].name = name.to_owned()
    };
    assert_eq!(caps(&renamed(3, "setattr")), not_registered);
    assert_eq!(caps(&renamed(5, "hasattr")), not_registered);
    assert_eq!(
        caps(&|r| r.facts.capabilities.constructs[6].status = ConstructSupport::Supported),
        not_registered
    );
    assert_eq!(
        caps(&|r| r.facts.capabilities.constructs[7].status = ConstructSupport::Supported),
        not_registered
    );
    assert_eq!(
        caps(&|r| r.facts.capabilities.constructs[8].status = ConstructSupport::Supported),
        not_registered
    );
    assert_eq!(
        caps(&|r| r.facts.capabilities.constructs[0].status = ConstructSupport::Partial),
        not_registered
    );
    assert_eq!(
        caps(&|r| r.facts.capabilities.constructs[1].status = ConstructSupport::Decided),
        not_registered
    );
    assert_eq!(
        caps(&|r| r.facts.capabilities.sections.push(SectionName::Bindings)),
        "source sections disagree with declared capabilities"
    );
    // The routes feature is optional, and an interface statement holds exactly with it.
    let unsupported = |r: &mut Reply| {
        if let Some(limits) = r.facts.profile_limits.as_mut() {
            limits.interface_boundary = archkeel_facts::envelope::LimitSupport::Unsupported;
        }
    };
    assert_eq!(
        caps(&unsupported),
        "an interface statement holds exactly with the feature import-routes-v1"
    );
}

#[test]
fn a_survey_with_a_gap_is_incomplete_and_its_gaps_must_be_its_unknowns() {
    use archkeel_facts::Section;

    let tree = project();
    fs::write(
        tree.root.join("src/app/client.py"),
        "import importlib\nimportlib.import_module(name)\n",
    )
    .unwrap();
    let original = reply(&tree);
    assert!(!original.facts.coverage.full_scope);
    assert_eq!(refusal(original.clone()), "");

    let mut partial = original.clone();
    for section in &mut partial.facts.sections {
        if let Section::Unknowns(records) = section {
            records.push(records[0].clone());
            records[1].id = archkeel_facts::ids::FactId::new("UNKNOWN-planted");
        }
    }
    assert!(!refusal(partial).is_empty());

    let mut hidden = original.clone();
    hidden.facts.coverage.gaps.clear();
    hidden.facts.coverage.full_scope = true;
    assert!(!refusal(hidden).is_empty());
}
