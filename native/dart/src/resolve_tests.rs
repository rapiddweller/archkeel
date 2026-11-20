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
fn an_inferred_type_of_a_literal_is_not_a_written_annotation_or_a_wire_fact() {
    let found = symbols(&[(
        "lib/routes.dart",
        "class Routes { static const path = '/'; }",
    )]);
    let field = found
        .symbols
        .iter()
        .find_map(|symbol| match &symbol.data {
            archkeel_facts::SymbolFact::Class(data) => data.attribute_declarations.first(),
            _ => None,
        })
        .expect("the field has a symbol");
    assert_eq!(field.annotation, None);
    let (actual, names) = field
        .inferred_builtin_type
        .as_ref()
        .expect("the literal proof");
    assert_eq!(actual, "dart.core.String");
    assert_eq!(names.get("String"), Some(actual));
    assert_eq!(names.get("int").map(String::as_str), Some("dart.core.int"));
    let mut wire = serde_json::to_value(field).expect("the wire field");
    assert!(wire.get("inferred_builtin_type").is_none());
    wire["inferred_builtin_type"] =
        serde_json::json!(["dart.core.String", {"String":"dart.core.String"}]);
    assert!(serde_json::from_value::<archkeel_facts::nested::AttributeDeclaration>(wire).is_err());
}

#[test]
fn an_untyped_final_local_infers_only_a_direct_nongeneric_constructor() {
    let found = symbols(&[
        ("lib/model.dart", "class Item {} class Box<T> {} typedef Alias = Item; class Factory { factory Factory() => _Impl(); } class _Impl implements Factory {}"),
        ("lib/another.dart", "class Item {}"),
        ("lib/main.dart", "import 'model.dart'; void main() { final plain = Item(); final alias = Alias(); final generic = Box<int>(); final factory = Factory(); final Item written = Item(); var mutable = Item(); } void shadowed(Item Function() Item) { final hidden = Item(); }"),
        ("lib/ambiguous.dart", "import 'model.dart'; import 'another.dart'; void probe() { final ambiguous = Item(); }"),
        ("lib/conditional.dart", "import 'model.dart' if (dart.library.io) 'missing.dart'; void probe() { final conditional = Item(); }"),
        ("lib/barrel.dart", "export 'model.dart';"),
        ("lib/reexport.dart", "import 'barrel.dart'; void probe() { final reexported = Item(); }"),
    ]);
    let mut proofs = Vec::new();
    for record in &found.calls {
        let archkeel_facts::CallFact::Call(data) = &record.data else {
            continue;
        };
        for binding in data.result_bindings.iter().flatten() {
            if let Some(inferred) = &binding.inferred_type {
                assert_eq!(binding.annotation, None);
                let mut wire = serde_json::to_value(binding).unwrap();
                assert!(wire.get("inferred_type").is_none());
                wire["inferred_type"] = serde_json::json!("Item");
                assert!(
                    serde_json::from_value::<archkeel_facts::nested::ResultBinding>(wire).is_err()
                );
                proofs.push((binding.name.as_str(), inferred.as_str()));
            }
        }
    }
    assert_eq!(proofs, [("plain", "Item")]);
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
            "part 'parted_part.dart';\nclass Parted {}\nclass Extended {}\nclass Derived extends Extended {}\n",
        ),
        (
            "lib/parted_part.dart",
            "part of 'parted.dart';\nextension E on Extended { void x() {} }\n",
        ),
        (
            "lib/unread.dart",
            "part 'unread_part.dart';\nclass Unread {}\n",
        ),
        (
            "lib/augmented.dart",
            "part 'augment_part.dart';\nclass Augmented {}\n",
        ),
        (
            "lib/augment_part.dart",
            "part of 'augmented.dart';\naugment class Augmented { void added() {} }\n",
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
    assert_eq!(
        status("shop.parted.Parted"),
        ("complete".to_owned(), String::new())
    );
    for qualified in ["shop.unread.Unread", "shop.augmented.Augmented"] {
        assert_eq!(
            status(qualified),
            (
                "partial".to_owned(),
                "not every part of the library was read".to_owned()
            )
        );
    }
    assert_eq!(status("shop.parted.Extended").0, "partial");
    assert_eq!(status("shop.parted.Derived").0, "partial");
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

/// Each declaration and member kind of the syntax has a binding kind of the same word.
#[test]
fn each_kind_of_the_syntax_is_a_binding_kind() {
    use crate::collection::types::BindingKind as B;
    use crate::resolve::binding_kind;
    use crate::syntax::{DefinitionKind as D, MemberKind as M};
    let definitions = [
        (D::Class, B::Class),
        (D::Interface, B::Interface),
        (D::Mixin, B::Mixin),
        (D::Enum, B::Enum),
        (D::Extension, B::Extension),
        (D::ExtensionType, B::ExtensionType),
        (D::Typedef, B::Typedef),
        (D::Function, B::Function),
        (D::Getter, B::Getter),
        (D::Setter, B::Setter),
        (D::Variable, B::Variable),
    ];
    for (kind, expected) in definitions {
        assert_eq!(binding_kind(&kind), expected);
    }
    let members = [
        (M::Field, B::Field),
        (M::Method, B::Method),
        (M::Constructor, B::Constructor),
        (M::Getter, B::Getter),
        (M::Setter, B::Setter),
        (M::Operator, B::Operator),
    ];
    for (kind, expected) in members {
        assert_eq!(binding_kind(&kind), expected);
    }
}
