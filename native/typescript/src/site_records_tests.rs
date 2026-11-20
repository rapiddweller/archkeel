// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: PR 4.3a-3d, which puts the records on the wire. The expected values follow the Python
// collector; `tests/test_collector_native_records.py` compares every record on real trees.

use archkeel_facts::envelope::Dirty;
use archkeel_facts::envelope::{Profile, Provenance};
use archkeel_facts::request::{Scope, Snapshot, TypeScriptRequest, TypeScriptSettings};
use archkeel_wire::protocol::Version;
use serde_json::Value;

use crate::collect::records;
use crate::collected::Records;
use crate::records_lists::{plains, Plain};
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

fn run(files: &[(&str, &str)]) -> Records {
    let mut all = vec![("tsconfig.json", r#"{"include":["src"]}"#)];
    all.extend_from_slice(files);
    let tree = Tree::new(&all);
    records(&request(&tree), provenance()).unwrap().1
}

fn call(found: &Records, expression: &str) -> Plain {
    plains(&found.calls)
        .into_iter()
        .find(|record| record.title == expression)
        .unwrap()
}

#[test]
fn the_anonymous_export_identity_does_not_resolve_calls_through_a_default_import() {
    let found = run(&[
        (
            "src/a.ts",
            "export default function (): number { return 1; }",
        ),
        (
            "src/b.ts",
            "import run from './a';\n\
             export function direct() { return run(); }\n\
             export function shadow(run: () => number) { return run(); }\n",
        ),
    ]);
    let calls = plains(&found.calls);
    assert_eq!(calls.len(), 2);
    for call in calls {
        assert_eq!(call.title, "run");
        assert_eq!(call.data["targets"], serde_json::json!([]));
    }
}

#[test]
fn const_arrow_is_a_callable_scope_but_jsx_registration_is_not_a_call() {
    let found = run(&[(
        "src/a.tsx",
        r#"
function request() {}
export const HelpButton = () => { request(); return <button onClick={request} />; };
function render() { HelpButton(); }
function shadow(HelpButton: () => void) { HelpButton(); }
"#,
    )]);
    let symbols = plains(&found.symbols);
    assert!(symbols
        .iter()
        .any(|item| item.kind == "function" && item.data["name"] == "HelpButton"));
    let calls = plains(&found.calls);
    let request = calls.iter().find(|item| item.title == "request").unwrap();
    assert_eq!(request.data["status"], "resolved");
    assert!(request.data["source_definition_id"].is_string());
    assert!(request.data["source_scope"]
        .as_str()
        .unwrap()
        .ends_with(".HelpButton"));
    let button_calls: Vec<_> = calls
        .iter()
        .filter(|item| item.title == "HelpButton")
        .collect();
    assert_eq!(button_calls.len(), 2);
    assert_eq!(button_calls[0].data["status"], "resolved");
    assert_eq!(button_calls[1].data["status"], "unresolved");
    assert_eq!(
        calls.iter().filter(|item| item.title == "request").count(),
        1
    );
}

#[test]
fn arrow_parameters_and_local_bindings_do_not_resolve_to_module_functions() {
    let found = run(&[(
        "src/a.tsx",
        r#"
function request() {}
export const Button = (request: () => void) => { request(); };
export const Other = () => { const request = () => {}; request(); };
"#,
    )]);
    let calls = plains(&found.calls);
    assert_eq!(calls.len(), 2);
    assert!(calls.iter().all(|item| item.data["status"] == "unresolved"));
}

#[test]
fn a_second_module_binding_prevents_a_proven_arrow_call() {
    let found = run(&[
        ("src/a.ts", "export const f = () => 1; var f = other; f();"),
        (
            "src/b.ts",
            "import { f as imported } from './a'; imported();",
        ),
    ]);
    for name in ["f", "imported"] {
        let data = call(&found, name).data;
        assert_eq!(data["status"], "partially_resolved");
        assert_eq!(data["candidate_count"], 1);
        assert_eq!(data["reason"], "module binding is ambiguous");
    }
}

#[test]
fn a_write_to_a_shadow_does_not_change_the_module_arrow() {
    let found = run(&[(
        "src/a.ts",
        "const f = () => 1; function other(f: () => number) { f = () => 2; } f();",
    )]);
    assert_eq!(call(&found, "f").data["status"], "resolved");
}

#[test]
fn duplicate_arrow_binding_in_a_script_is_not_a_proven_call() {
    let found = run(&[("src/a.ts", "const f = () => 1; var f = other; f();")]);
    assert_ne!(call(&found, "f").data["status"], "resolved");
}

#[test]
fn a_function_with_a_second_module_binding_is_not_a_proven_call() {
    let found = run(&[("src/a.ts", "function f() {} let f = other; f();")]);
    assert_ne!(call(&found, "f").data["status"], "resolved");
}

#[test]
fn an_import_with_a_second_module_binding_is_not_a_proven_call() {
    let found = run(&[
        ("src/a.ts", "export function f() {}"),
        ("src/b.ts", "import { f } from './a'; let f = other; f();"),
    ]);
    assert_ne!(call(&found, "f").data["status"], "resolved");
}

#[test]
fn reassignment_and_hook_result_are_not_proven_const_arrow_calls() {
    let found = run(&[
        ("src/a.tsx", "export const changed = () => 1; function mutate() { changed = () => 2; }"),
        ("src/b.tsx", "import { changed } from './a'; function useCallback(f: () => void) { return f; } const handler = useCallback(() => {}); changed(); handler();"),
    ]);
    assert_eq!(call(&found, "changed").data["status"], "unresolved");
    assert_eq!(call(&found, "handler").data["status"], "unresolved");
}

#[test]
fn an_inline_jsx_handler_does_not_prove_the_component_calls_its_body() {
    let found = run(&[(
        "src/a.tsx",
        "function request() {} export const Button = () => <button onClick={() => request()} />;",
    )]);
    assert_ne!(call(&found, "request").data["status"], "resolved");
}

#[test]
fn public_react_help_button_has_a_symbol_without_a_handler_call() {
    // Excalidraw, MIT, 701b901a: packages/excalidraw/components/HelpButton.tsx.
    let found = run(&[(
        "src/help.tsx",
        r#"export const HelpButton = (props: HelpButtonProps) => (
  <Tooltip label={`${t("helpDialog.title")} — ?`} delay>
    <button className="help-icon" onClick={props.onClick} type="button"
      aria-label={t("helpDialog.title")}>
      {HelpIcon}
    </button>
  </Tooltip>
);"#,
    )]);
    assert!(plains(&found.symbols)
        .iter()
        .any(|item| item.kind == "function" && item.data["name"] == "HelpButton"));
    assert!(!plains(&found.calls)
        .iter()
        .any(|item| item.title == "props.onClick"));
}

#[test]
fn a_call_of_a_local_function_resolves_and_a_second_definition_makes_it_partial() {
    let found = run(&[(
        "src/a.ts",
        "function f() {}\nfunction g() {}\nfunction g() {}\nf(); g(); h();\n",
    )]);
    let data = |name: &str| call(&found, name).data;
    assert_eq!(data("f")["status"], "resolved");
    assert_eq!(data("f")["candidate_count"], 1);
    assert_eq!(data("g")["status"], "partially_resolved");
    assert_eq!(
        data("g")["reason"],
        "multiple definition sites share the target name"
    );
    assert_eq!(data("h")["status"], "unresolved");
    assert_eq!(data("h")["reason"], "definition is missing or ambiguous");
    assert!(data("f").get("source_definition_id").is_none());
}

#[test]
fn a_shadowed_a_rebound_and_a_computed_name_keep_their_reason() {
    let found = run(&[(
        "src/a.ts",
        "function f() {}\nfunction w(f) { f(); }\nlet g = 1; g = 2;\nfunction g() {}\ng();\nobj[f]();\n",
    )]);
    let calls = plains(&found.calls);
    let reasons: Vec<(&str, &str)> = calls
        .iter()
        .map(|record| {
            (
                record.title.as_str(),
                record
                    .data
                    .get("reason")
                    .and_then(Value::as_str)
                    .unwrap_or(""),
            )
        })
        .collect();
    assert!(reasons.contains(&("f", "lexical binding may shadow the name")));
    assert!(reasons.contains(&("g", "name is rebound in module scope")));
    assert!(reasons.iter().any(|(title, _)| title.starts_with("obj[")));
}

#[test]
fn a_this_member_resolves_to_the_field_of_its_class_and_an_import_to_the_exporting_file() {
    let found = run(&[
        ("src/a.ts", "export function one() {}\nexport class Box {}\n"),
        (
            "src/b.ts",
            "import { one, Box } from './a';\nclass K { f = 1; m() { return this.f + this.nope; } }\n\
             one(); const b = new Box();\n",
        ),
    ]);
    let references = plains(&found.references);
    let this_refs: Vec<(&str, &str)> = references
        .iter()
        .filter(|record| record.title.starts_with("this."))
        .map(|record| {
            (
                record.title.as_str(),
                record.data["status"].as_str().unwrap(),
            )
        })
        .collect();
    assert_eq!(
        this_refs,
        [("this.f", "resolved"), ("this.nope", "unresolved")]
    );
    let imported = call(&found, "one");
    assert_eq!(imported.data["status"], "resolved");
    assert!(imported.data["targets"][0]
        .as_str()
        .unwrap()
        .ends_with("a_x2e_ts.one"));
}

#[test]
fn a_new_expression_assigned_to_a_name_makes_a_construction_and_a_value_binding() {
    let found = run(&[("src/a.ts", "class C {}\nconst c: C = new C();\nnew C();\n")]);
    assert_eq!(found.bindings.len(), 1);
    assert!(found.bindings[0].id.as_str().starts_with("VALUEBIND-"));
    assert!(found.bindings[0].title.ends_with(".c binding"));
    let calls = plains(&found.calls);
    let news: Vec<&Plain> = calls.iter().filter(|record| record.title == "C").collect();
    assert_eq!(news.len(), 2);
    assert_eq!(news[0].data["construction"]["status"], "resolved");
    assert_eq!(news[0].data["result_bindings"][0]["annotation"], "C");
    assert_eq!(news[1].data["result_bindings"], Value::Array(vec![]));
}

#[test]
fn a_construction_of_a_name_with_two_classes_is_partial_and_a_hidden_export_is_not_imported() {
    let found = run(&[
        ("src/a.ts", "function hidden() {}\nexport function shown() {}\n"),
        (
            "src/b.ts",
            "import { hidden, shown } from './a';\nclass D {}\nclass D {}\nnew D(); hidden(); shown();\n",
        ),
    ]);
    let new_d = call(&found, "D");
    assert_eq!(new_d.data["status"], "partially_resolved");
    assert_eq!(new_d.data["construction"]["status"], "partially_resolved");
    assert_eq!(call(&found, "hidden").data["status"], "unresolved");
    assert_eq!(call(&found, "shown").data["status"], "resolved");
}
