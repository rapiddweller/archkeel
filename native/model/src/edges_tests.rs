// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The edges of slice S2 (`aggregate_edges`) and the split of the imports (`split_imports`).

use std::io::{Read, Write};

use archkeel_facts::envelope::{FileFact, Reply, Target};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::sections::{GapFact, ImportFact, Section};
use archkeel_facts::Record;
use flate2::read::GzDecoder;
use flate2::write::ZlibEncoder;
use flate2::Compression;

use super::{both, Edge, Level};
use crate::imports::{split, Import, Resolved};

fn import(id: &str, from: (&str, &str), to: (&str, &str), type_checking: bool) -> Import {
    Import {
        reexport_chain: Vec::new(),
        id: id.to_owned(),
        source_module: from.0.to_owned(),
        target_module: to.0.to_owned(),
        source_package: from.1.to_owned(),
        target_package: to.1.to_owned(),
        under_type_checking: type_checking,
        symbol: None,
        symbols_known: true,
        relative: false,
        resolved: Resolved::Local,
        evidence: Vec::new(),
    }
}

fn file(module: &str, package: &str) -> FileFact {
    FileFact {
        id: FactId::new(format!("FILE-{module}")),
        rel_path: format!("{module}.ts"),
        module: ModuleName::new(module),
        package: PackageName::new(package),
        all_exports: Vec::new(),
        all_literal: false,
        compatibility_logic_free: false,
        stable_bindings: Vec::new(),
        blank: false,
        evidence_id: EvidenceId::new(format!("EVD-{module}")),
    }
}

/// The modules `shop.a.x`, `shop.a.y` (package `shop.a`) and `shop.b.z` (package `shop.b`).
fn files() -> Vec<FileFact> {
    vec![
        file("shop.a.x", "shop.a"),
        file("shop.a.y", "shop.a"),
        file("shop.b.z", "shop.b"),
    ]
}

const X: (&str, &str) = ("shop.a.x", "shop.a");
const Y: (&str, &str) = ("shop.a.y", "shop.a");
const Z: (&str, &str) = ("shop.b.z", "shop.b");

fn pairs(edges: &[Edge]) -> Vec<(&str, &str)> {
    edges.iter().map(|e| (e.source(), e.target())).collect()
}

#[test]
fn a_self_import_gives_no_edge_at_either_level() {
    let (modules, packages) = both(&files(), &[import("I1", X, X, false)], "shop");
    assert!(modules.is_empty());
    assert!(packages.is_empty());
    // Two modules of one package give a module edge and no package edge.
    let (modules, packages) = both(&files(), &[import("I1", X, Y, false)], "shop");
    assert_eq!(pairs(&modules), vec![("shop.a.x", "shop.a.y")]);
    assert!(packages.is_empty());
}

#[test]
fn a_module_edge_needs_a_module_of_the_reply_and_a_package_edge_the_namespace() {
    let outside = ("shop.c.gone", "shop.c");
    let (modules, packages) = both(&files(), &[import("I1", X, outside, false)], "shop");
    assert!(modules.is_empty());
    assert_eq!(pairs(&packages), vec![("shop.a", "shop.c")]);
    // A package that only starts with the namespace text is outside it.
    let foreign = ("shopping.lib", "shopping");
    let (modules, packages) = both(&files(), &[import("I1", X, foreign, false)], "shop");
    assert!(modules.is_empty() && packages.is_empty());
}

#[test]
fn the_imports_of_one_pair_give_one_edge_with_both_counts() {
    let imports = [
        import("I2", X, Z, true),
        import("I1", X, Z, false),
        import("I3", Y, Z, true),
    ];
    let (modules, packages) = both(&files(), &imports, "shop");
    assert_eq!(
        pairs(&modules),
        vec![("shop.a.x", "shop.b.z"), ("shop.a.y", "shop.b.z")]
    );
    let first = &modules[0];
    assert_eq!(first.imports(), ["I1", "I2"]);
    assert_eq!((first.type_checking(), first.runtime()), (1, 1));
    assert_eq!((modules[1].type_checking(), modules[1].runtime()), (1, 0));
    assert_eq!(pairs(&packages), vec![("shop.a", "shop.b")]);
    assert_eq!(packages[0].imports(), ["I1", "I2", "I3"]);
    assert_eq!((packages[0].type_checking(), packages[0].runtime()), (2, 1));
}

#[test]
fn an_edge_is_bidirectional_only_when_its_reverse_exists() {
    let imports = [import("I1", X, Z, false), import("I2", Z, X, false)];
    let (modules, _) = both(&files(), &imports, "shop");
    assert!(modules.iter().all(Edge::bidirectional));
    let (modules, _) = both(&files(), &imports[..1], "shop");
    assert!(!modules[0].bidirectional());
}

#[test]
fn a_package_edge_uses_the_packages_of_the_import_record() {
    // A nested module: its package is not the parent of its module name in the record.
    let nested = ("shop.b.z", "shop.b.deep");
    let (_, packages) = both(&files(), &[import("I1", X, nested, false)], "shop");
    assert_eq!(pairs(&packages), vec![("shop.a", "shop.b.deep")]);
    assert_eq!(packages[0].level(), Level::Package);
}

#[test]
fn the_edge_id_is_the_stable_id_of_the_reference_engine() {
    let (from, to) = (("shop.a", "shop.a"), ("shop.b", "shop.b"));
    let files = [file("shop.a", "shop.a"), file("shop.b", "shop.b")];
    let (modules, packages) = both(&files, &[import("I1", from, to, false)], "shop");
    // `stable_id("EDGE", "module", "shop.a", "shop.b")` of `ir/facts.py`.
    assert_eq!(modules[0].id(), "EDGE-b046d2adb373145b");
    assert_eq!(packages[0].id(), "EDGE-43e62772497b6040");
}

/// The typed facts of the frozen H-typescript reply (AD-343).
fn golden() -> Option<Reply> {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/golden/typescript/h-typescript.json.gz"
    );
    let mut text = String::new();
    GzDecoder::new(std::fs::File::open(path).ok()?)
        .read_to_string(&mut text)
        .ok()?;
    // The edits of `eval_tests.rs`: the store accepts the frozen reply with them.
    let mut value: serde_json::Value = serde_json::from_str(&text).ok()?;
    let facts = &mut value["facts"];
    facts["adapter"]["version"] = serde_json::json!("0");
    facts["adapter"]["code_digest"] = serde_json::json!("0".repeat(64));
    facts["runtime"] = serde_json::json!({"name": "rust", "version": "1.88.0",
        "required": null, "requirement_state": "declared"});
    facts["source"]["git_head"] = serde_json::json!("a");
    facts["source"]["dirty"] = serde_json::json!(false);
    facts["provider_bindings"] = serde_json::json!([]);
    value["protocol_version"] = serde_json::json!("9.0.0");
    value["provider_sources"] = serde_json::json!([]);
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
    encoder.write_all(value.to_string().as_bytes()).ok()?;
    let bytes = encoder.finish().ok()?;
    let ingested = archkeel_store::ingest_reply(&bytes, 1 << 30).ok()?;
    Some(ingested.reply().clone())
}

fn import_records(reply: &mut Reply) -> Option<&mut Vec<Record<ImportFact>>> {
    reply
        .facts
        .sections
        .iter_mut()
        .find_map(|section| match section {
            Section::Imports(records) => Some(records),
            _ => None,
        })
}

#[test]
fn supported_profile_does_not_remove_the_per_import_symbol_check(
) -> Result<(), Box<dyn std::error::Error>> {
    use crate::{Cause, Decision, Graph, Model, Producer, Reason, Settings, Verdict};
    use archkeel_contract::ParsedContract;
    use archkeel_facts::envelope::{LimitSupport, ProfileLimits};

    let mut reply = golden().ok_or("the golden reply")?;
    reply.facts.runtime.required = Some(">=1.88".to_owned());
    reply.facts.profile_limits = Some(ProfileLimits {
        dependency_symbols: LimitSupport::Supported,
        interface_boundary: LimitSupport::Supported,
    });
    let id = reply
        .facts
        .imports
        .iter()
        .find_map(|target| match target {
            Target::Local { import_id, .. } => Some(import_id.clone()),
            _ => None,
        })
        .ok_or("a local import")?;
    let selected = import_records(&mut reply)
        .ok_or("imports")?
        .iter()
        .find(|record| record.id == id)
        .ok_or("the selected import")?
        .data
        .data();
    let contract = serde_json::json!({
        "schema_version": "3.14.0", "components": [{"id": "COMP-APP", "label": "app",
        "role": "component", "packages": ["shop"], "responsibilities": ["Own the source."],
        "forbidden_responsibilities": [], "provenance": ["p"], "decided_by": "architect"}],
        "rules": [{"id": "SYMBOL", "kind": "forbidden_dependency",
        "source": selected.source_module, "target": selected.target_module,
        "target_symbol": "blocked", "include_type_checking": true,
        "rationale": "Keep the boundary.", "provenance": ["p"], "decided_by": "architect"}]
    });
    let ParsedContract::Complete(contract) =
        archkeel_contract::parse(contract.to_string().as_bytes())?
    else {
        return Err("a complete contract".into());
    };
    for known in [true, false] {
        let selected = import_records(&mut reply)
            .ok_or("imports")?
            .iter_mut()
            .find(|record| record.id == id)
            .ok_or("the selected import")?
            .data
            .data_mut();
        selected.symbol = None;
        selected.symbols_known = known;
        let settings = Settings::new(
            "shop".to_owned(),
            reply.facts.profile.as_str().to_owned(),
            vec![],
        )
        .with_producer(Producer::Trusted);
        let graph = Graph::recorded(&reply.facts, settings).map_err(|r| r.to_string())?;
        let model = Model::of(&contract, graph).map_err(|r| r.1.to_string())?;
        let rule = contract.rules().first().ok_or("the selector rule")?;
        let decision = model.scope(|scope| match scope.complete(rule) {
            Ok(proof) => scope.pass(proof),
            Err(reason) => Decision::unknown(reason),
        });
        assert_eq!(
            matches!(decision.verdict(), Verdict::Pass(_)),
            known,
            "{decision:?}"
        );
        if !known {
            assert_eq!(decision.verdict(), &Verdict::Unknown);
            assert_eq!(
                decision.reason(),
                Some(&Reason::NotComplete(Cause::Undecided(1)))
            );
        }
    }
    Ok(())
}

/// The golden reply with its first import unresolved; the id and site of that import.
fn unresolved() -> Option<(Reply, String, String, Vec<EvidenceId>)> {
    let mut reply = golden()?;
    let record = import_records(&mut reply)?.first()?.clone();
    let id = record.id.as_str().to_owned();
    let target = reply
        .facts
        .imports
        .iter_mut()
        .find(|target| target.import_id().as_str() == id)?;
    *target = Target::Unresolved {
        import_id: FactId::new(&id),
        specifier: "./gone".to_owned(),
        reason: "Unresolved module: ./gone".to_owned(),
    };
    let module = record.data.data().source_module.as_str().to_owned();
    Some((reply, id, module, record.evidence_ids))
}

#[test]
fn an_unresolved_import_leaves_the_imports_and_counts_unless_a_gap_names_its_site() {
    let Some((mut reply, id, module, evidence)) = unresolved() else {
        return fail("the golden reply");
    };
    let total = import_records(&mut reply).map_or(0, |records| records.len());
    let found = split(&reply.facts);
    let (imports, unknown) = (found.imports, found.unknown);
    assert_eq!(unknown, 1);
    assert_eq!(imports.len() + 1, total);
    assert!(imports.iter().all(|import| import.id() != id));
    // A gap of the imports at the same module and evidence names the site.
    let gap = GapFact::resolution("Unresolved module: ./gone", &module);
    let mut record = Record::unknown(FactId::new("UNKNOWN-G"), "gone", None, &module, gap);
    record.evidence_ids = evidence;
    reply.facts.coverage.gaps.push(record.clone());
    assert_eq!(split(&reply.facts).unknown, 0);
    // A gap at the same module with other evidence names another site.
    record.evidence_ids = vec![EvidenceId::new("EVD-other")];
    reply.facts.coverage.gaps = vec![record];
    assert_eq!(split(&reply.facts).unknown, 1);
}

#[test]
fn a_macro_body_is_no_import_and_no_unknown() {
    let Some(mut reply) = golden() else {
        return fail("the golden reply");
    };
    let Some(records) = import_records(&mut reply) else {
        return fail("an imports section");
    };
    let total = records.len();
    if let Some(first) = records.first_mut() {
        first.data = ImportFact::MacroBody(first.data.data().clone());
    }
    let pair = records.first().map(|record| {
        let data = record.data.data();
        (
            data.source_module.as_str().to_owned(),
            data.target_module.as_str().to_owned(),
        )
    });
    let found = split(&reply.facts);
    assert_eq!((found.imports.len() + 1, found.unknown), (total, 0));
    // The macro body stays as a row of its own, for the fan counts of the modules.
    let bodies: Vec<(String, String)> = found
        .macro_bodies
        .iter()
        .map(|body| {
            (
                body.source_module().to_owned(),
                body.target_module().to_owned(),
            )
        })
        .collect();
    assert_eq!(bodies, pair.into_iter().collect::<Vec<_>>());
}

#[test]
fn the_import_keeps_the_typed_target_and_the_type_check_flag() {
    let Some(mut reply) = golden() else {
        return fail("the golden reply");
    };
    let flags: Vec<bool> = import_records(&mut reply)
        .map(|records| {
            records
                .iter()
                .map(|r| r.data.data().under_type_checking)
                .collect()
        })
        .unwrap_or_default();
    let ids: Vec<String> = reply
        .facts
        .imports
        .iter()
        .map(|t| t.import_id().as_str().to_owned())
        .collect();
    if let [first, second, ..] = reply.facts.imports.as_mut_slice() {
        *first = Target::External {
            import_id: FactId::new(&ids[0]),
            package: PackageName::new("@x/y"),
        };
        *second = Target::Builtin {
            import_id: FactId::new(&ids[1]),
            name: "fs".to_owned(),
        };
    }
    let imports = split(&reply.facts).imports;
    let resolved = |id: &str| {
        imports
            .iter()
            .find(|i| i.id() == id)
            .map(|i| i.resolved().clone())
    };
    assert_eq!(
        resolved(&ids[0]),
        Some(Resolved::External("@x/y".to_owned()))
    );
    assert_eq!(resolved(&ids[1]), Some(Resolved::Builtin));
    assert_eq!(resolved(&ids[2]), Some(Resolved::Local));
    let kept: Vec<bool> = imports.iter().map(Import::under_type_checking).collect();
    assert_eq!(kept, flags);
    assert!(flags.contains(&true) && flags.contains(&false));
}

/// Fail the test with a message (clippy refuses `panic!` in this workspace).
fn fail(message: &str) {
    assert_eq!(message, "", "the test setup failed");
}

#[test]
fn an_unresolved_macro_body_counts_as_an_unknown_import() {
    let Some((mut reply, id, _, _)) = unresolved() else {
        return fail("the golden reply");
    };
    let Some(records) = import_records(&mut reply) else {
        return fail("an imports section");
    };
    for record in records.iter_mut().filter(|r| r.id.as_str() == id) {
        record.data = ImportFact::MacroBody(record.data.data().clone());
    }
    assert_eq!(split(&reply.facts).unknown, 1);
}

#[test]
fn the_evidence_of_an_import_is_sorted_and_the_gap_site_keeps_the_reply_order() {
    let Some((mut reply, id, module, _)) = unresolved() else {
        return fail("the golden reply");
    };
    let unsorted = vec![EvidenceId::new("EVD-b"), EvidenceId::new("EVD-a")];
    let Some(records) = import_records(&mut reply) else {
        return fail("an imports section");
    };
    for record in records.iter_mut() {
        record.evidence_ids = unsorted.clone();
    }
    let imports = split(&reply.facts).imports;
    assert!(imports.iter().all(|i| i.evidence() == ["EVD-a", "EVD-b"]));
    // A gap with the sorted evidence names another site than the import with the reply order.
    let gap = GapFact::resolution("gone", &module);
    let mut record = Record::unknown(FactId::new("UNKNOWN-G"), "gone", None, &module, gap);
    record.evidence_ids = vec![EvidenceId::new("EVD-a"), EvidenceId::new("EVD-b")];
    reply.facts.coverage.gaps = vec![record.clone()];
    assert_eq!(split(&reply.facts).unknown, 1, "{id}");
    record.evidence_ids = unsorted;
    reply.facts.coverage.gaps = vec![record];
    assert_eq!(split(&reply.facts).unknown, 0);
}

#[test]
fn only_two_accepted_profiles_have_typed_target_marks() {
    // The reference engine marks an external and a builtin target for two profiles (AD-372). Each
    // other profile that the store accepts must read its targets by module (AD-450).
    use archkeel_facts::envelope::{Profile, TargetMarks};
    let Some(golden) = golden() else {
        return fail("the golden reply");
    };
    let accepted: Vec<Profile> = Profile::ALL
        .iter()
        .copied()
        .filter(|profile| {
            let mut reply = golden.clone();
            reply.facts.profile = *profile;
            let text = serde_json::to_string(&reply).unwrap_or_default();
            let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
            let _ = encoder.write_all(text.as_bytes());
            let bytes = encoder.finish().unwrap_or_default();
            let name = profile.as_str();
            !archkeel_store::ingest_reply(&bytes, 1 << 30)
                .err()
                .is_some_and(|message| message.contains(&format!("does not check {name} replies")))
        })
        .collect();
    let typed = accepted
        .iter()
        .filter(|profile| profile.target_marks() == TargetMarks::Typed)
        .count();
    assert_eq!(typed, 2, "{accepted:?}");
    // AD-468: the store also checks Dart replies; Python and Dart read targets by module.
    assert_eq!(accepted.len(), 4, "{accepted:?}");
}
