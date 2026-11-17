// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The namespace of a library (AD-796), through the survey: each plant is a Dart package that
//! `dart analyze` accepts.

use serde_json::Value;

use crate::import_survey::tests::run_roots;
use crate::import_survey::Survey;

const PUBSPEC: &str = "name: shop\nenvironment:\n  sdk: ^3.4.0\n";

fn symbols(files: &[(&str, &str)]) -> Survey {
    let mut all = vec![("pubspec.yaml", PUBSPEC)];
    all.extend_from_slice(files);
    run_roots(&all, &["lib"])
}

/// The data of the symbol `qualified`, as the facts write it.
fn data(found: &Survey, qualified: &str) -> Value {
    let record = found
        .symbols
        .iter()
        .map(|record| serde_json::to_value(record).unwrap())
        .find(|record| record["data"]["qualified_name"] == qualified);
    record.map_or(Value::Null, |record| record["data"].clone())
}

fn bases(found: &Survey, qualified: &str) -> Vec<(String, String)> {
    data(found, qualified)["base_declarations"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|base| {
            (
                base["status"].as_str().unwrap_or("").to_owned(),
                base["targets"].to_string(),
            )
        })
        .collect()
}

#[test]
fn a_base_binds_through_show_prefix_and_export() {
    let found = symbols(&[
        ("lib/model.dart", "class Base {}\nclass _Hidden {}\n"),
        ("lib/api.dart", "export 'model.dart' show Base;\n"),
        (
            "lib/a.dart",
            "import 'api.dart';\nclass A extends Base {}\n",
        ),
        (
            "lib/b.dart",
            "import 'model.dart' as m;\nclass B extends m.Base {}\n",
        ),
        (
            "lib/c.dart",
            "import 'model.dart' hide Base;\nclass Base {}\nclass C extends Base {}\n",
        ),
        (
            "lib/d.dart",
            "import 'api.dart' hide Base;\nclass D extends Object {}\n",
        ),
    ]);
    assert_eq!(
        bases(&found, "shop.a.A"),
        [("resolved".to_owned(), r#"["shop.model.Base"]"#.to_owned())]
    );
    assert_eq!(
        bases(&found, "shop.b.B"),
        [("resolved".to_owned(), r#"["shop.model.Base"]"#.to_owned())]
    );
    // A declaration of the library hides an import of the same name.
    assert_eq!(
        bases(&found, "shop.c.C"),
        [("resolved".to_owned(), r#"["shop.c.Base"]"#.to_owned())]
    );
    // A base outside the snapshot stays unresolved.
    assert_eq!(
        bases(&found, "shop.d.D"),
        [("unresolved".to_owned(), "[]".to_owned())]
    );
}

#[test]
fn a_field_formal_takes_the_type_of_its_field() {
    let found = symbols(&[(
        "lib/order.dart",
        "class Line {\n  const Line(this.sku, {this.count = 1});\n  final String sku;\n  final int count;\n}\n",
    )]);
    let constructor = data(&found, "shop.order.Line.Line");
    let parameters = constructor["parameters"]
        .as_array()
        .cloned()
        .unwrap_or_default();
    let written: Vec<(String, String)> = parameters
        .iter()
        .map(|p| {
            (
                p["name"].as_str().unwrap_or("").to_owned(),
                p["annotation"].to_string(),
            )
        })
        .collect();
    assert_eq!(
        written,
        [
            ("sku".to_owned(), r#""String""#.to_owned()),
            ("count".to_owned(), r#""int""#.to_owned())
        ]
    );
}

#[test]
fn an_inventory_is_partial_when_a_form_outside_the_body_can_add_members() {
    let found = symbols(&[
        (
            "lib/plain.dart",
            "class Plain {\n  int a = 0;\n  void m() {}\n}\n",
        ),
        ("lib/mixed.dart", "mixin M {}\nclass Mixed with M {}\n"),
        (
            "lib/parted.dart",
            "part 'parted_part.dart';\nclass Parted {}\n",
        ),
        ("lib/parted_part.dart", "part of 'parted.dart';\n"),
        (
            "lib/extended.dart",
            "class Extended {}\nextension E on Extended {\n  void x() {}\n}\n",
        ),
        // An extension type wraps its representation and adds no member to it.
        (
            "lib/wrap.dart",
            "import 'plain.dart';\nextension type Wrap(Plain p) {}\n",
        ),
    ]);
    let status = |qualified: &str| {
        let inventories = data(&found, qualified)["member_inventories"].clone();
        let first = &inventories[0];
        (
            first["status"].as_str().unwrap_or("absent").to_owned(),
            first["reason"].as_str().unwrap_or("").to_owned(),
        )
    };
    assert_eq!(
        status("shop.plain.Plain"),
        ("complete".to_owned(), String::new())
    );
    assert!(
        status("shop.mixed.Mixed").1.contains("mixin"),
        "{:?}",
        status("shop.mixed.Mixed")
    );
    assert!(
        status("shop.parted.Parted").1.contains("part"),
        "{:?}",
        status("shop.parted.Parted")
    );
    assert_eq!(status("shop.extended.Extended").0, "partial");
}

/// The store checks that a symbol name is the last segment of its qualified name (AD-796).
#[test]
fn each_symbol_of_the_fixtures_is_named_by_its_last_segment() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fixtures");
    let mut bad = Vec::new();
    for (fixture, namespace) in [
        ("G-dart", "shop"),
        ("I-flutter-shop", "shop"),
        ("J-compass", "compass"),
    ] {
        let root = root.join(fixture).canonicalize().unwrap();
        let request = serde_json::json!({
            "protocol_version": "8.0.0",
            "snapshot": {"root": root.to_str().unwrap(), "git_head": "0".repeat(40), "dirty": false},
            "scope": {"roots": ["lib"], "namespace": namespace},
            "resolver": {"language": "dart"},
        });
        let request = crate::import_survey::reply::decode(request.to_string().as_bytes()).unwrap();
        let found = crate::import_survey::survey(&request).unwrap();
        for record in &found.symbols {
            let value = serde_json::to_value(record).unwrap();
            let name = value["data"]["name"].as_str().unwrap_or("").to_owned();
            let qualified = value["data"]["qualified_name"]
                .as_str()
                .unwrap_or("")
                .to_owned();
            if qualified.rsplit('.').next() != Some(name.as_str()) {
                bad.push(format!("{fixture} {} {name} {qualified}", value["kind"]));
            }
        }
    }
    assert!(bad.is_empty(), "{}", bad.join("\n"));
}

/// The grammar reads no augmentation: the file is a syntax gap and gives no symbol, so no
/// inventory of its classes can be complete (AD-796).
#[test]
fn an_augmentation_is_a_syntax_gap_and_gives_no_symbol() {
    let found = symbols(&[(
        "lib/a.dart",
        "class C {\n  void m() {}\n}\naugment class C {\n  void z() {}\n}\n",
    )]);
    assert!(found.symbols.is_empty());
    assert!(!found.coverage.full_scope);
}
