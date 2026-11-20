// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the declarations of AD-518. The plants of the hard forms against release 4.0.1 are in
// `tests/test_cli_python_symbols.py`; these tests pin the forms that need Python 3.12 and the
// facts that the model reads.

use archkeel_facts::vocab::{ClassKind, InventoryStatus, MethodKind};
use archkeel_facts::{FactData, SymbolFact};

use super::*;
use crate::survey::binders::Binders;

fn declared(text: &str, minor: u32) -> Vec<Record<SymbolFact>> {
    let module = crate::test_module(text, minor);
    let binders = Binders::of(&module.tree);
    let _ = minor;
    records(
        &module,
        &binders,
        escapes::all(
            std::slice::from_ref(&module),
            std::slice::from_ref(&binders),
            &[],
        )
        .remove(0),
        None,
        &mut EvidenceMap::new(),
    )
    .records
}

fn names(found: &[Record<SymbolFact>]) -> Vec<String> {
    let mut all: Vec<String> = found
        .iter()
        .filter_map(|record| record.data.fields().qualified_name.map(str::to_owned))
        .collect();
    all.sort();
    all
}

#[test]
fn a_type_statement_binds_its_name_and_the_function_is_not_written() {
    let found = declared("def f():\n    pass\n\n\ntype f = int\n", 12);
    assert!(names(&found).is_empty(), "{:?}", names(&found));
}

#[test]
fn a_class_with_type_parameters_has_no_kind() {
    let found = declared("class A[T]:\n    def m(self):\n        pass\n", 12);
    assert!(names(&found).is_empty());
}

#[test]
fn a_function_with_type_parameters_is_written_with_its_signature_text() {
    let found = declared("def f[T](a: T) -> T:\n    return a\n", 12);
    assert_eq!(names(&found), ["app.probe.f"]);
}

#[test]
fn each_record_names_its_parent_and_its_kind() {
    let text = "from enum import Enum\n\n\nclass A:\n    x: int = 1\n    class B:\n        pass\n\n    @staticmethod\n    def s():\n        pass\n\n\nclass E(Enum):\n    R = 1\n";
    let found = declared(text, 11);
    assert_eq!(
        names(&found),
        [
            "app.probe.A",
            "app.probe.A.B",
            "app.probe.A.s",
            "app.probe.E"
        ]
    );
    for record in &found {
        match &record.data {
            SymbolFact::Class(data) if data.name == "E" => {
                assert_eq!(data.class_kind, Some(ClassKind::Enum));
                assert_eq!(data.enum_members, Some(vec!["R".to_owned()]));
            }
            SymbolFact::Class(data) if data.name == "A" => {
                assert_eq!(data.class_kind, Some(ClassKind::Class));
                assert_eq!(data.attribute_declarations.len(), 1);
            }
            SymbolFact::Class(data) => assert_eq!(data.parent.as_deref(), Some("app.probe.A")),
            SymbolFact::Method(data) => {
                assert_eq!(data.method_kind, Some(MethodKind::Static));
                assert_eq!(data.parent.as_deref(), Some("app.probe.A"));
            }
            other => assert!(matches!(other, SymbolFact::Function(_)), "{other:?}"),
        }
    }
}

#[test]
fn a_member_list_is_never_stated_complete() {
    let found = declared(
        "class A:\n    x = 1\n\n    def m(self):\n        pass\n",
        11,
    );
    let SymbolFact::Class(data) = &found
        .iter()
        .find(|record| matches!(record.data, SymbolFact::Class(_)))
        .expect("the class has a record")
        .data
    else {
        return;
    };
    assert_eq!(data.member_inventories.len(), 2);
    assert!(data
        .member_inventories
        .iter()
        .all(|item| item.status == InventoryStatus::Partial && item.reason.is_some()));
}

#[test]
fn an_attribute_write_with_another_base_than_self_writes_no_member() {
    let open = declared("class A:\n    x = 1\n\n\nA.y = 2\n", 11);
    assert_eq!(names(&open), ["app.probe.A"]);
    let own = declared(
        "class A:\n    x = 1\n\n    def m(self):\n        self.y = 2\n",
        11,
    );
    assert_eq!(names(&own), ["app.probe.A", "app.probe.A.m"]);
}

#[test]
fn a_text_that_the_reader_does_not_write_leaves_the_signature_unread_not_the_module() {
    let found = declared(
        concat!(
            "def f(a: list[int]) -> int:\n    pass\n\n\ndef g(a: int = None) -> None:\n    pass\n\n\n",
            "def h(a: int = None, b: 'x.y' = True) -> a.b:\n    pass\n"
        ),
        11,
    );
    assert_eq!(names(&found), ["app.probe.f", "app.probe.g", "app.probe.h"]);
    let mut complete: Vec<(String, Option<bool>)> = found
        .iter()
        .filter_map(|record| match &record.data {
            SymbolFact::Function(data) => Some((data.name.clone(), data.signature_complete)),
            _ => None,
        })
        .collect();
    complete.sort();
    assert_eq!(
        complete,
        [
            ("f".to_owned(), Some(false)),
            ("g".to_owned(), Some(true)),
            ("h".to_owned(), Some(false))
        ]
    );
    let plain = declared(
        "def h(a: int = None, b: x.y = True) -> a.b:\n    pass\n",
        11,
    );
    assert_eq!(names(&plain), ["app.probe.h"]);
}

const M: &str = "\n    def m(self):\n        pass\n";

#[test]
fn a_class_that_a_name_use_escapes_keeps_no_member() {
    let called = declared(&format!("class A:{M}\n\nA()\nA.m\n"), 11);
    assert_eq!(names(&called), ["app.probe.A", "app.probe.A.m"]);
    let kept = declared(
        &format!("class A:{M}\n\ndef f(a: A) -> A:\n    return A()\n"),
        11,
    );
    assert_eq!(
        names(&kept),
        ["app.probe.A", "app.probe.A.m", "app.probe.f"]
    );
    let passed = declared(&format!("class A:{M}\n\nprint(A)\n"), 11);
    assert_eq!(names(&passed), ["app.probe.A"]);
}

#[test]
fn a_write_through_a_base_that_may_be_a_class_opens_the_module() {
    let metaclass = declared(
        &format!("class M(type):\n    def f(self):\n        self.y = 1\n\n\nclass A:{M}"),
        11,
    );
    assert_eq!(names(&metaclass), ["app.probe.A"]);
    let hook = declared(
        &format!("class A:{M}\n    def __init_subclass__(self):\n        self.y = 1\n"),
        11,
    );
    assert_eq!(names(&hook), ["app.probe.A"]);
    let setter = declared(&format!("class A:{M}\n\ntype.__setattr__(A, 'm', 2)\n"), 11);
    assert_eq!(names(&setter), ["app.probe.A"]);
    let own = declared(
        &format!("class A:{M}\n    def n(self):\n        self.y = 1\n"),
        11,
    );
    assert_eq!(
        names(&own),
        ["app.probe.A", "app.probe.A.m", "app.probe.A.n"]
    );
}

#[test]
fn a_bare_annotation_is_a_declaration_but_mangled_names_and_aliases_are_not() {
    let found = declared(
        "class A:\n    __x = 1\n    y: int\n    z = print\n    def __w(self):\n        pass\n",
        11,
    );
    let SymbolFact::Class(data) = &found[0].data else {
        return;
    };
    assert_eq!(names(&found), ["app.probe.A"]);
    // AD-748 treats the bare annotation as a structural declaration.
    assert_eq!(data.attribute_declarations.len(), 1);
    assert_eq!(data.attribute_declarations[0].name, "y");
    let alias = declared(
        "from enum import Enum\n\n\nclass E(Enum):\n    R = 1\n    S = 1.0\n",
        11,
    );
    let SymbolFact::Class(data) = &alias[0].data else {
        return;
    };
    assert!(data.enum_members.is_none() && data.attribute_declarations.is_empty());
}

/// The call and reference sites of a module that needs Python 3.12.
fn sites_of(text: &str) -> (Vec<archkeel_facts::Record<archkeel_facts::CallFact>>, usize) {
    let module = crate::test_module(text, 12);
    let binders = Binders::of(&module.tree);
    let escapes = escapes::all(
        std::slice::from_ref(&module),
        std::slice::from_ref(&binders),
        &[],
    )
    .remove(0);
    let mut evidence = EvidenceMap::new();
    let found = records(&module, &binders, escapes, None, &mut evidence);
    let none = std::collections::HashSet::new();
    let context = Context::collect(std::slice::from_ref(&found), (&[], &[]), (&none, &none));
    let sites = site_records(
        (&module, &binders),
        &found,
        (&context, &super::DirectMethods::default()),
        &mut evidence,
    );
    (sites.calls, sites.references.len())
}

fn resolved(calls: &[archkeel_facts::Record<archkeel_facts::CallFact>]) -> usize {
    calls
        .iter()
        .filter(|record| match &record.data {
            archkeel_facts::CallFact::Calls(data) => {
                data.status == archkeel_facts::vocab::Status::Resolved
            }
            _ => false,
        })
        .count()
}

#[test]
fn a_type_parameter_hides_the_module_symbol_in_its_body_and_its_annotations() {
    let hidden = "def helper():\n    pass\n\n\ndef run[helper]():\n    helper()\n";
    let (calls, _) = sites_of(hidden);
    assert_eq!((calls.len(), resolved(&calls)), (1, 0));
    let plain = "def helper():\n    pass\n\n\ndef run():\n    helper()\n";
    assert_eq!(resolved(&sites_of(plain).0), 1);
    let ann = "class U:\n    pass\n\n\ndef build[U]() -> U:\n    pass\n";
    assert_eq!(sites_of(ann).1, 0);
    let free = "class U:\n    pass\n\n\ndef build() -> U:\n    pass\n";
    assert_eq!(sites_of(free).1, 1);
}

#[test]
fn a_nested_function_without_a_module_target_stays_unresolved() {
    let source = "def run():\n    def helper():\n        pass\n    helper()\n";
    let calls = sites_of(source).0;
    assert!(matches!(&calls[0].data, archkeel_facts::CallFact::Calls(_)));
    let archkeel_facts::CallFact::Calls(data) = &calls[0].data else {
        return;
    };

    assert_eq!(data.status, archkeel_facts::vocab::Status::Unresolved);
}

#[test]
fn a_decorated_nested_function_stays_unresolved() {
    let source = "def helper():\n    pass\n\n\ndef replace(_):\n    return helper\n\n\ndef run():\n    @replace\n    def helper():\n        pass\n    helper()\n";
    let calls = sites_of(source).0;
    assert!(matches!(&calls[0].data, archkeel_facts::CallFact::Calls(_)));
    let archkeel_facts::CallFact::Calls(data) = &calls[0].data else {
        return;
    };

    assert_eq!(data.status, archkeel_facts::vocab::Status::Unresolved);
}
