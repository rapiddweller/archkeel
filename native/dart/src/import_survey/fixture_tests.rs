// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the wiring of Dart into `archkeel-collect` (#880). The survey of each Dart fixture
// of the repository is pinned: the files, the parts, the edges and the gaps by name (AD-450).
// A change of a count is a change of the survey and needs its reason.

use std::collections::BTreeMap;
use std::path::Path;

use serde_json::json;

use super::{edge_rows, gap_rows, survey};

fn surveyed(fixture: &str, namespace: &str) -> (usize, usize, usize, BTreeMap<String, usize>) {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures")
        .join(fixture);
    let root = root.canonicalize().unwrap();
    let request = json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": root.to_str().unwrap(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": namespace},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    assert_eq!(found.imports.len(), edge_rows(&found).len());
    let gaps = gap_rows(&found);
    (
        found.files.len(),
        found.parts.len(),
        found.imports.len(),
        gaps,
    )
}

#[test]
fn the_dart_fixtures_give_the_pinned_survey() {
    let none = BTreeMap::new();
    assert_eq!(surveyed("G-dart", "shop"), (9, 1, 22, none.clone()));
    assert_eq!(surveyed("H-uml-dart", "commerce"), (8, 0, 12, none.clone()));
    assert_eq!(surveyed("I-flutter-shop", "shop"), (21, 0, 73, none));
    let workspace = BTreeMap::from([
        ("DartPathDependency".to_owned(), 1),
        ("DartWorkspace".to_owned(), 1),
    ]);
    assert_eq!(surveyed("J-compass", "compass"), (89, 22, 433, workspace));
}
