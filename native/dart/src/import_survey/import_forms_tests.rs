// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the wiring of Dart into `archkeel-collect` (#880, AD-1263). The edges that the survey
// gives for each form of a Dart directive, by the rules of Dart and the files that exist. The
// expected edges are written here, not read from an earlier output.

use archkeel_snapshot::test_tree::Tree;
use serde_json::json;

use super::{edge_rows, gap_rows, survey};

const PUBSPEC: &str = "name: shop\nenvironment:\n  sdk: ^3.4.0\n";

fn surveyed(files: &[(&str, &str)]) -> super::Survey {
    let mut all = vec![("pubspec.yaml", PUBSPEC)];
    all.extend_from_slice(files);
    let tree = Tree::new(&all);
    let request = json!({
        "protocol_version": "9.0.0",
        "snapshot": {"root": tree.path(), "git_head": "0".repeat(40), "dirty": false},
        "scope": {"roots": ["lib"], "namespace": "shop", "exclude_test_sources": false},
        "resolver": {"language": "dart"},
    });
    survey(&crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap()).unwrap()
}

#[test]
fn each_form_of_a_directive_gives_the_edges_that_dart_defines() {
    let main = "import 'dart:io';\n\
        import 'package:http/http.dart' as http;\n\
        import 'package:shop/b.dart' show B;\n\
        import './d.dart';\n\
        import 'c.dart' deferred as c;\n\
        import 'stub.dart' if (dart.library.io) 'io.dart';\n\
        export 'e.dart' hide Hidden;\n\
        part 'main_part.dart';\n";
    let found = surveyed(&[
        ("lib/main.dart", main),
        ("lib/main_part.dart", "part of 'main.dart';\n"),
        ("lib/b.dart", ""),
        ("lib/c.dart", ""),
        ("lib/d.dart", ""),
        ("lib/e.dart", ""),
        ("lib/stub.dart", ""),
        ("lib/io.dart", ""),
    ]);
    // A platform, a package, a `package:` path of this package and a relative path name modules; a
    // deferred import is an import; a conditional import names each library that it may load; an
    // export is a re-export; a part is no edge: it belongs to its library.
    assert_eq!(
        edge_rows(&found),
        [
            "shop.main export shop.e",
            "shop.main import dart.io",
            "shop.main import http.http",
            "shop.main import shop.b",
            "shop.main import shop.c",
            "shop.main import shop.d",
            "shop.main import shop.io",
            "shop.main import shop.stub",
        ]
    );
    assert_eq!(found.parts.len(), 1);
    assert!(gap_rows(&found).is_empty(), "{:?}", gap_rows(&found));
}

#[test]
fn an_import_of_a_file_that_does_not_exist_is_a_gap_and_no_edge_to_a_module() {
    let found = surveyed(&[("lib/a.dart", "import 'gone.dart';\n")]);
    assert!(!edge_rows(&found)
        .iter()
        .any(|row| row.ends_with("shop.gone")));
    assert!(!gap_rows(&found).is_empty());
}
