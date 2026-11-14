// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the declarations of AD-514. The plants of the hard forms against release 4.0.1 are in
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
    records(&module, &binders, &mut EvidenceMap::new())
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
    let text = "from enum import Enum\n\n\nclass A:\n    x: int\n    class B:\n        pass\n\n    @staticmethod\n    def s():\n        pass\n\n\nclass E(Enum):\n    R = 1\n";
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
fn a_text_that_the_reader_does_not_write_gives_no_record_of_its_declaration() {
    let found = declared(
        concat!(
            "def f(a: list[int]) -> int:\n    pass\n\n\ndef g(a: int = 1) -> None:\n    pass\n\n\n",
            "def h(a: int = None, b: 'x.y' = True) -> a.b:\n    pass\n"
        ),
        11,
    );
    assert_eq!(names(&found), Vec::<String>::new());
    let plain = declared(
        "def h(a: int = None, b: x.y = True) -> a.b:\n    pass\n",
        11,
    );
    assert_eq!(names(&plain), ["app.probe.h"]);
}
