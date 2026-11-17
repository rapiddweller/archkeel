// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the wiring of Dart into `archkeel-collect` (#880). The survey of each Dart fixture
// of the repository is pinned: the files, the parts, the edge set and the gaps by name (AD-454).
// The edge sets in `fixture_edges/` equal the import edges of release 4.0.1 on these fixtures.
// A change of a count is a change of the survey and needs its reason. AD-749: a `show` list gives
// one record for each name, so G-dart has 24 records (22 before) on the same 22 edges.

use std::collections::BTreeMap;
use std::path::Path;

use serde_json::json;

use super::{edge_rows, gap_rows, survey};

fn surveyed(fixture: &str, namespace: &str) -> (usize, usize, usize, BTreeMap<String, usize>) {
    // J-compass keeps the flutter/samples workspace layout: the app is below `compass_app/app`.
    let scan = if fixture == "J-compass" {
        "compass_app/app/lib"
    } else {
        "lib"
    };
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures")
        .join(fixture);
    let root = root.canonicalize().unwrap();
    let request = json!({
        "protocol_version": "8.0.0",
        "snapshot": {"root": root.to_str().unwrap(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": [scan], "namespace": namespace},
        "resolver": {"language": "dart"},
    });
    let found =
        survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap())
            .unwrap();
    let pinned: Vec<&str> = match fixture {
        "G-dart" => include_str!("fixture_edges/G-dart.txt"),
        "H-uml-dart" => include_str!("fixture_edges/H-uml-dart.txt"),
        "I-flutter-shop" => include_str!("fixture_edges/I-flutter-shop.txt"),
        _ => include_str!("fixture_edges/J-compass.txt"),
    }
    .lines()
    .collect();
    assert_eq!(
        edge_rows(&found),
        pinned,
        "{fixture}: the edge set differs from the pin"
    );
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
    assert_eq!(surveyed("G-dart", "shop"), (9, 1, 24, none.clone()));
    assert_eq!(surveyed("H-uml-dart", "commerce"), (8, 0, 12, none.clone()));
    assert_eq!(
        surveyed("I-flutter-shop", "shop"),
        (21, 0, 73, none.clone())
    );
    // AD-808 and #1752: J-compass keeps the workspace layout of flutter/samples, and the scan
    // reads its workspace root, so the 105 package gaps of the old layout (AD-800) are gone.
    assert_eq!(surveyed("J-compass", "compass"), (89, 22, 433, none));
}
