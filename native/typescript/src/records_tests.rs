// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: PR 4.3a-3d, which puts the records on the wire. The expected values follow the Python
// collector; `tests/test_collector_native_records.py` compares every record on real trees.

use archkeel_facts::envelope::Dirty;
use archkeel_facts::envelope::{Profile, Provenance};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::request::{Scope, Snapshot, TypeScriptRequest, TypeScriptSettings};
use archkeel_facts::Section;
use archkeel_wire::protocol::Version;

use crate::collect::{collect, records};
use crate::collected::import_section;
use crate::records_lists::plains;
use archkeel_snapshot::test_tree::Tree;

fn request(tree: &Tree) -> TypeScriptRequest {
    TypeScriptRequest {
        protocol_version: Version::V9,
        snapshot: Snapshot {
            root: tree.path(),
            git_head: "a".repeat(40),
            dirty: Dirty::Known(false),
        },
        scope: Scope {
            roots: vec!["src".to_owned()],
            namespace: "shop".to_owned(),
            exclude_test_sources: Some(false),
        },
        resolver: TypeScriptSettings {
            tsconfig: "tsconfig.json".to_owned(),
            bundler: false,
        },
    }
}

fn provenance() -> Provenance {
    Provenance::native(
        Profile::TypeScript,
        ("0+unknown", &"0".repeat(64)),
        ("1.88.0", "1.88"),
    )
}

const CONFIG: &str = r#"{"compilerOptions":{"module":"commonjs"},"include":["src"]}"#;

#[test]
fn expanding_imports_keeps_a_proven_script_global_name() {
    let tree = Tree::new(&[
        ("tsconfig.json", r#"{"compilerOptions":{"allowJs":true},"include":["src"]}"#),
        ("src/a.js", "var Shapes; (function (Shapes) { Shapes.circle = function (r) { return r; }; Shapes.unit = 1; })(Shapes || (Shapes = {}));"),
        ("src/b.js", "var area = Shapes.circle(Shapes.unit); var missing = Shapes.absent;"),
    ]);
    let (plain, _) = crate::collect::gather(&request(&tree), provenance());
    let before: Vec<_> = import_section(&plain)
        .iter()
        .filter(|r| matches!(r.data, archkeel_facts::ImportFact::ScriptGlobal(_)))
        .collect();
    assert!(before.iter().any(|r| r.data.data().symbols_known));
    let (_, found) = records(&request(&tree), provenance()).unwrap();
    let globals: Vec<_> = found
        .imports
        .iter()
        .filter(|r| matches!(r.data, archkeel_facts::ImportFact::ScriptGlobal(_)))
        .collect();
    assert!(!globals.is_empty());
    assert_eq!(
        serde_json::to_value(globals).unwrap(),
        serde_json::to_value(before).unwrap()
    );
}

#[test]
fn type_publication_preserves_complete_value_and_overload_records() {
    for (before, after) in [
        ("\nexport const Published = 1;", "export type Published = number;\nexport const Published = 1;"),
        ("export function Published(x: number): number;\nexport function Published(x: number) { return x; }",
         "export function Published(x: number): number;\nexport function Published(x: number) { return x; }\nexport interface Other {}"),
    ] {
        let read = |source: &str| {
            let tree = Tree::new(&[("tsconfig.json", CONFIG), ("src/a.ts", source),
                ("src/b.ts", "import { Published } from './a';")]);
            let (_, rows) = records(&request(&tree), provenance()).unwrap();
            assert!(rows.imports.iter().all(|r| r.data.data().symbols_known));
            assert_eq!(rows.witnesses.len(), 1);
            serde_json::to_value((&rows.imports, &rows.witnesses)).unwrap()
        };
        assert_eq!(read(before), read(after));
    }
}

#[test]
fn a_type_hop_cites_each_publication_and_an_unread_type_stays_unknown() {
    for api in [
        "export type { Published } from './a';",
        "export * from './a';",
    ] {
        let tree = Tree::new(&[
            ("tsconfig.json", CONFIG),
            ("src/a.ts", "export interface Published {}"),
            ("src/api.ts", api),
            ("src/b.ts", "import type { Published } from './api';"),
        ]);
        let (_, rows) = records(&request(&tree), provenance()).unwrap();
        let import = rows
            .imports
            .iter()
            .find(|r| r.data.data().symbol.as_deref() == Some("Published"))
            .unwrap();
        let proven = !api.contains('*');
        assert_eq!(import.data.data().symbols_known, proven);
        assert_eq!(import.fact_ids.len(), if proven { 2 } else { 0 });
        for id in &import.fact_ids {
            let witness = rows.witnesses.iter().find(|r| &r.id == id).unwrap();
            assert_eq!(
                serde_json::to_value(witness).unwrap()["data"]["name"],
                "Published"
            );
            assert_eq!(witness.evidence_ids.len(), 2);
        }
        assert_eq!(
            import.data.data().reexport_chain.as_ref().unwrap().len(),
            if proven { 2 } else { 0 }
        );
    }
}

#[test]
fn the_linked_reply_states_its_profile_limits_but_wire_bytes_cannot_carry_them() {
    use archkeel_facts::envelope::{LimitSupport, Reply};
    for source in ["export const one = 1;", "const one = 1;"] {
        let tree = Tree::new(&[("tsconfig.json", CONFIG), ("src/a.ts", source)]);
        let reply = crate::typed_reply(&request(&tree), provenance(), Version::V9).unwrap();
        let limits = reply.facts.profile_limits.unwrap();
        assert_eq!(limits.interface_boundary, LimitSupport::Supported);
        let symbols = reply
            .facts
            .capabilities
            .resolution_features
            .iter()
            .any(|feature| feature == "script-globals-v1");
        assert_eq!(
            limits.dependency_symbols == LimitSupport::Supported,
            symbols
        );
        let saved = serde_json::to_vec(&reply).unwrap();
        let replay: Reply = serde_json::from_slice(&saved).unwrap();
        assert!(replay.facts.profile_limits.is_none());
    }
}

#[test]
fn a_statement_with_bound_names_becomes_one_record_for_each_name() {
    let tree = Tree::new(&[
        ("tsconfig.json", CONFIG),
        ("src/a.ts", "export const one = 1;\nexport const two = 2;\n"),
        (
            "src/b.ts",
            "import { one, two as t } from './a';\nfunction f(k) { return k === 'x'; }\n",
        ),
    ]);
    let (facts, found) = records(&request(&tree), provenance()).unwrap();
    let bound: Vec<_> = found
        .imports
        .iter()
        .filter(|record| record.id.as_str().starts_with("IMP_BINDING-"))
        .collect();
    assert_eq!(bound.len(), 2);
    assert!(bound[0].data.data().symbols_known);
    assert_eq!(found.witnesses.len(), 2);
    assert!(found
        .witnesses
        .iter()
        .all(|w| w.id.as_str().starts_with("ESM_EXPORT-")));
    assert_eq!(bound[0].fact_ids.len(), 1);
    assert_eq!(found.targets.len(), found.imports.len());
    // The id of the first name is the id of its statement with the ordinal 0.
    let (plain, _) = crate::collect::gather(&request(&tree), provenance());
    let parent = import_section(&plain)
        .iter()
        .find(|record| record.title.ends_with("imports ./a"))
        .unwrap();
    let first = stable_id(
        "IMP_BINDING",
        &[Part::Text(parent.id.as_str()), Part::Number(0)],
    );
    assert!(found
        .imports
        .iter()
        .any(|record| record.id.as_str() == first));
    assert_eq!(found.constructs.len(), 1);
    // The owner of a comparison is the definition that holds it.
    assert!(plains(&found.constructs)[0].data["owner"]
        .as_str()
        .unwrap()
        .ends_with("_x2e_ts.f"));
    assert!(found.constructs[0]
        .title
        .ends_with(" compares a written string literal"));
    // The reply holds all of them, in the order of the capability.
    let names: Vec<_> = facts.sections.iter().map(Section::name).collect();
    assert_eq!(
        names,
        [
            "imports",
            "unknowns",
            "symbols",
            "calls",
            "references",
            "bindings",
            "constructs"
        ]
    );
}

#[test]
fn a_namespace_a_type_only_name_and_a_name_of_a_broken_file_are_not_proven() {
    let tree = Tree::new(&[
        ("tsconfig.json", CONFIG),
        ("src/a.ts", "export const one = 1;\n"),
        ("src/broken.ts", "export const ok = 1;\nexport const = ;\n"),
        (
            "src/b.ts",
            "import * as ns from './a';\nimport type { one } from './a';\nimport { ok } from './broken';\n",
        ),
    ]);
    let (_, found) = records(&request(&tree), provenance()).unwrap();
    assert!(found.witnesses.is_empty());
    let known: Vec<bool> = found
        .imports
        .iter()
        .filter(|record| record.id.as_str().starts_with("IMP_BINDING-"))
        .map(|record| record.data.data().symbols_known)
        .collect();
    assert_eq!(known, [false; 3]);
}

#[test]
fn a_collection_declares_the_inner_uml_capability_and_fills_each_section_that_it_declares() {
    let tree = Tree::new(&[
        ("tsconfig.json", CONFIG),
        (
            "src/a.ts",
            "export const one = 1;\nexport function f() {}\n",
        ),
        (
            "src/b.ts",
            "import { one, f } from './a';\nclass K { m() { f(); return one === 'x'; } }\n",
        ),
    ]);
    let facts = collect(&request(&tree), provenance());
    let names: Vec<&str> = facts.sections.iter().map(Section::name).collect();
    assert_eq!(
        names,
        [
            "imports",
            "unknowns",
            "symbols",
            "calls",
            "references",
            "bindings",
            "constructs"
        ]
    );
    let count = |name: &str| {
        facts
            .sections
            .iter()
            .find(|section| section.name() == name)
            .map_or(0, Section::len)
    };
    // Every declared section has records here: nothing is claimed that is not produced.
    for name in [
        "imports",
        "symbols",
        "calls",
        "references",
        "bindings",
        "constructs",
    ] {
        assert!(count(name) > 0, "{name}");
    }
    assert!(import_section(&facts)
        .iter()
        .all(|r| r.id.as_str().starts_with("IMP_BINDING-")));
    assert_eq!(facts.imports.len(), count("imports"));
    assert_eq!(facts.features[4], "inner-uml-v1");
    // A proven binding has a witness, and a witness is what earns the feature.
    assert_eq!(facts.features[5], "script-globals-v1");
    assert_eq!(facts.constructs, [("string_literal_compare", "partial")]);
}

#[test]
fn the_streamed_reply_and_the_lists_run_one_producer() {
    let tree = Tree::new(&[
        ("tsconfig.json", CONFIG),
        ("src/a.ts", "export const one = 1;\nexport function f() {}\n"),
        (
            "src/b.ts",
            "import { one, f } from './a';\nclass K { m() { f(); return one === 'x'; } }\nnew K();\n",
        ),
    ]);
    let request = request(&tree);
    let mut streamed = Vec::new();
    crate::collect::reply(&request, provenance(), Version::V9, &mut streamed).unwrap();
    let listed = collect(&request, provenance());
    // The reply is a zlib stream, and the lists hold the seven declared sections.
    assert_eq!(streamed[0], 0x78);
    assert_eq!(listed.sections.len(), 7);
}

#[test]
fn the_bindings_section_holds_the_witnesses_and_the_result_bindings() {
    let tree = Tree::new(&[
        ("tsconfig.json", CONFIG),
        ("src/a.ts", "export class K {}\nexport const one = 1;\n"),
        (
            "src/b.ts",
            "import { K, one } from './a';\nconst made = new K();\nexport const x = one;\n",
        ),
    ]);
    let (facts, found) = records(&request(&tree), provenance()).unwrap();
    let bindings = &facts.sections[5];
    assert_eq!(bindings.name(), "bindings");
    // The witnesses come first, then the bindings of the `new` expressions.
    assert_eq!(bindings.len(), found.witnesses.len() + found.bindings.len());
    assert!(found.witnesses.len() >= 2);
    assert_eq!(found.bindings.len(), 1);
    assert!(found.bindings[0].id.as_str().starts_with("VALUEBIND-"));
    assert_eq!(plains(&found.bindings)[0].data["binding"], "made");
}
