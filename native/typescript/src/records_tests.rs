// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: PR 4.3a-3d, which puts the records on the wire. The expected values follow the Python
// collector; `tests/test_collector_native_records.py` compares every record on real trees.

use archkeel_wire::identity::{stable_id, Part};
use archkeel_wire::protocol::Version;
use archkeel_wire::reply::Provenance;
use archkeel_wire::request::Request;
use serde_json::Value;

use crate::collect::{collect, records, PROFILE};
use crate::test_tree::Tree;

fn request(tree: &Tree) -> Request {
    Request {
        version: Version::V9,
        root: tree.path(),
        git_head: "a".repeat(40),
        dirty: Value::Bool(false),
        roots: vec!["src".to_owned()],
        namespace: "shop".to_owned(),
        exclude_test_sources: false,
        tsconfig: "tsconfig.json".to_owned(),
        bundler: false,
    }
}

fn provenance() -> Provenance {
    Provenance {
        profile: PROFILE,
        adapter_version: "0+unknown".to_owned(),
        code_digest: "0".repeat(64),
        runtime_name: "rust",
        runtime_version: "1.88.0".to_owned(),
        runtime_required: ">=1.88".to_owned(),
    }
}

const CONFIG: &str = r#"{"compilerOptions":{"module":"commonjs"},"include":["src"]}"#;

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
    let (facts, found) = records(&request(&tree), provenance());
    let bound: Vec<_> = found
        .imports
        .iter()
        .filter(|record| record.id.starts_with("IMP_BINDING-"))
        .collect();
    assert_eq!(bound.len(), 2);
    assert_eq!(bound[0].data["symbols_known"], true);
    assert_eq!(found.witnesses.len(), 2);
    assert!(found
        .witnesses
        .iter()
        .all(|w| w.id.starts_with("ESM_EXPORT-")));
    assert_eq!(bound[0].fact_ids.len(), 1);
    assert_eq!(found.targets.len(), found.imports.len());
    // The id of the first name is the id of its statement with the ordinal 0.
    let statement = &collect(&request(&tree), provenance()).sections[0].1;
    let parent = statement
        .iter()
        .find(|record| record.title.ends_with("imports ./a"))
        .unwrap();
    let first = stable_id("IMP_BINDING", &[Part::Text(&parent.id), Part::Number(0)]);
    assert!(found.imports.iter().any(|record| record.id == first));
    assert_eq!(found.constructs.len(), 1);
    // The owner of a comparison is the definition that holds it.
    assert!(found.constructs[0].data["owner"]
        .as_str()
        .unwrap()
        .ends_with("_x2e_ts.f"));
    assert!(found.constructs[0]
        .title
        .ends_with(" compares a written string literal"));
    // The reply of the same collection does not hold any of them.
    assert!(facts
        .sections
        .iter()
        .all(|(name, _)| ["imports", "unknowns"].contains(name)));
    assert!(facts.constructs.is_empty());
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
    let (_, found) = records(&request(&tree), provenance());
    assert!(found.witnesses.is_empty());
    let known: Vec<&Value> = found
        .imports
        .iter()
        .filter(|record| record.id.starts_with("IMP_BINDING-"))
        .map(|record| &record.data["symbols_known"])
        .collect();
    assert_eq!(known, [&Value::Bool(false); 3]);
}

#[test]
fn a_plain_collection_keeps_nothing_for_the_records() {
    let tree = Tree::new(&[
        ("tsconfig.json", CONFIG),
        ("src/a.ts", "export const one = 1;\n"),
        ("src/b.ts", "import { one } from './a';\n"),
    ]);
    let facts = collect(&request(&tree), provenance());
    let imports = &facts.sections[0].1;
    // One record for the statement, as before: the reply is the legacy reply.
    assert_eq!(imports.len(), 1);
    assert!(imports[0].id.starts_with("IMP-"));
    assert_eq!(facts.features.len(), 4);
}
