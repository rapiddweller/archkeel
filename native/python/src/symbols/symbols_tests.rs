// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::collections::HashSet;

use ruff_text_size::TextSize;

use super::*;

fn records(source: &str, minor: u32) -> Vec<Value> {
    let tree = crate::parse::parse(source, minor).expect("the probe parses");
    let module = Module::new("src/app/m.py".into(), "app.m".into(), source.into(), tree);
    let exports = HashSet::from(["f".to_owned()]);
    match table(&module, &exports, minor, true, &mut EvidenceMap::new()) {
        Table::Records(records) => records,
        Table::Gap { file, reason } => vec![json!({"gap": reason, "file": file})],
    }
}

fn by_name<'a>(records: &'a [Value], name: &str) -> &'a Value {
    records
        .iter()
        .find(|record| record["data"]["qualified_name"] == name)
        .expect("the record exists")
}

#[test]
fn a_definition_has_the_location_of_its_keyword_after_the_decorators() {
    let source = "@a\n# c\n@b\n\nasync def f(): pass\n";
    let found = records(source, 12);
    let def = by_name(&found, "app.m.f");
    let module = Module::new(
        "src/app/m.py".into(),
        "app.m".into(),
        source.into(),
        crate::parse::parse(source, 12).expect("the probe parses"),
    );
    let mut evidence = EvidenceMap::new();
    let start = TextSize::from(11);
    let id = module.evidence(&mut evidence, &ruff_text_size::TextRange::new(start, start));
    assert_eq!(def["evidence_ids"], json!([id]));
    assert_eq!(evidence.values().next().map(|item| item.line), Some(5));
    assert_eq!(def["data"]["declared_in_all"], json!(true));
    assert_eq!(def["data"]["async"], json!(true));
}

#[test]
fn an_elif_and_a_handler_are_contexts_of_their_own() {
    let found = records(
        "if a:\n    pass\nelif b:\n    def f(): pass\ntry:\n    pass\nexcept E:\n    class C: pass\n",
        12,
    );
    let contexts = |name| by_name(&found, name)["data"]["definition_contexts"].clone();
    let kinds = |value: Value| -> Vec<(String, String)> {
        value
            .as_array()
            .into_iter()
            .flatten()
            .map(|item| (item["kind"].to_string(), item["branch"].to_string()))
            .collect()
    };
    assert_eq!(
        kinds(contexts("app.m.f")),
        [
            ("\"if\"".into(), "\"else\"".into()),
            ("\"if\"".into(), "\"body\"".into())
        ]
    );
    assert_eq!(
        kinds(contexts("app.m.C")),
        [("\"try\"".into(), "\"handler\"".into())]
    );
}

#[test]
fn a_nested_function_is_neither_a_method_nor_bound_in_a_namespace() {
    let found = records(
        "class C:\n    def m(self):\n        def inner(): pass\n",
        12,
    );
    let method = by_name(&found, "app.m.C.m");
    assert_eq!(method["kind"], json!("method"));
    assert_eq!(method["data"]["namespace_bound"], json!(true));
    let inner = by_name(&found, "app.m.C.m.inner");
    assert_eq!(inner["kind"], json!("function"));
    assert_eq!(inner["data"]["namespace_bound"], json!(false));
    assert_eq!(inner["data"]["lexical_parent_id"], method["id"]);
}

#[test]
fn a_deep_default_gives_a_gap_and_no_record() {
    let deep = vec!["a"; 150].join(" + ");
    let found = records(&format!("def f(x={deep}): pass\n"), 12);
    assert_eq!(found.len(), 1);
    assert_eq!(found[0]["file"], json!("src/app/m.py"));
    assert!(found[0]["gap"]
        .as_str()
        .is_some_and(|gap| gap.contains("RecursionError")));
}

#[test]
fn the_visibility_of_a_special_name_is_public() {
    assert_eq!(class::visibility("__init__")["kind"], json!("public"));
    assert_eq!(class::visibility("____")["kind"], json!("private"));
    assert_eq!(class::visibility("_x")["kind"], json!("private"));
}

fn gap_of(source: &str, minor: u32) -> Option<String> {
    let found = records(source, minor);
    found
        .first()
        .and_then(|item| item["gap"].as_str().map(str::to_owned))
}

#[test]
fn a_string_that_native_cannot_write_gives_a_gap_with_its_own_reason() {
    let surrogate = gap_of("def f(d=f'\\ud800{x}'): pass\n", 12);
    assert!(surrogate.is_some_and(|gap| gap.contains("surrogate")));
    let spec = gap_of("def f(d=f'{xy:\\N{BULLET}}'): pass\n", 12);
    assert!(spec.is_some_and(|gap| gap.contains("3.12")));
    assert_eq!(gap_of("def f(d=f'{xy:\\N{BULLET}}'): pass\n", 13), None);
    let unused = gap_of("x = f'{a:{b:{c:{d}}}}'\nclass C: pass\n", 13);
    assert!(unused.is_some_and(|gap| gap.contains("two levels")));
}

#[test]
fn a_version_outside_3_11_to_3_14_gives_a_gap() {
    for minor in [10, 15] {
        let found = records_unparsed("class C: pass\n", minor);
        assert!(found.is_some_and(|gap| gap.contains("3.11 to 3.14")));
    }
}

/// The table of a module parsed as 3.14, read with the rules of `minor`.
fn records_unparsed(source: &str, minor: u32) -> Option<String> {
    let tree = crate::parse::parse(source, 14).expect("the probe parses");
    let module = Module::new("src/app/m.py".into(), "app.m".into(), source.into(), tree);
    match table(
        &module,
        &HashSet::new(),
        minor,
        true,
        &mut EvidenceMap::new(),
    ) {
        Table::Gap { reason, .. } => Some(reason),
        Table::Records(_) => None,
    }
}
