// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Tests for call counts.

use super::{count, FileMeasures};
use crate::survey::binders::Binders;
use crate::survey::Survey;

fn measured<'a>(survey: &'a Survey, module: &str) -> &'a FileMeasures {
    survey
        .coverage
        .measures
        .iter()
        .flatten()
        .find(|row| row.module.as_str() == module)
        .unwrap()
}

#[test]
fn counts_nested_decorated_and_dynamic_calls() {
    let module = crate::test_module(
        "@decorate(factory())\ndef f(self, x):\n    return self.m(x()) + obj.m() + f()()\n",
        11,
    );
    let binders = Binders::of(&module.tree);
    let row = count(
        &module,
        &binders,
        &[],
        &super::Context::default(),
        &mut Vec::new(),
    );
    assert_eq!(row.calls_total, 8);
    assert_eq!(row.calls_unresolved, 8);
    assert_eq!(row.unresolved_self, 1);
    assert_eq!(row.unresolved_attribute, 1);
    assert_eq!(row.unresolved_dynamic, 2);
}

#[test]
fn a_rebound_builtin_is_not_proven() {
    let module = crate::test_module("len = custom\nlen([])\n", 11);
    let binders = Binders::of(&module.tree);
    let row = count(
        &module,
        &binders,
        &[],
        &super::Context::default(),
        &mut Vec::new(),
    );
    assert_eq!((row.calls_builtin, row.calls_unresolved), (0, 1));
}

#[test]
fn survey_counts_are_stable_when_input_order_changes() {
    let files = [
        ("src/app/__init__.py", ""),
        ("src/app/one.py", "def make():\n    return 1\n"),
        ("src/app/two.py", "from app.one import make\nimport json\ndef f():\n    make()\n    json.dumps({})\n    self.m()\n"),
    ];
    let first = crate::survey::targets::tests::surveyed(&files);
    let mut reverse = files;
    reverse.reverse();
    let second = crate::survey::targets::tests::surveyed(&reverse);
    assert_eq!(first.coverage.measures, second.coverage.measures);
    let row = measured(&first, "app.two");
    assert_eq!(
        (
            row.calls_total,
            row.calls_resolved,
            row.calls_external,
            row.calls_unresolved
        ),
        (3, 1, 1, 1)
    );
}

#[test]
fn adding_an_unproved_receiver_increases_only_the_unresolved_count() {
    let a = crate::test_module("def f(x):\n    return x\n", 11);
    let b = crate::test_module("def f(x):\n    return x.m()\n", 11);
    let before = count(
        &a,
        &Binders::of(&a.tree),
        &[],
        &super::Context::default(),
        &mut Vec::new(),
    );
    let after = count(
        &b,
        &Binders::of(&b.tree),
        &[],
        &super::Context::default(),
        &mut Vec::new(),
    );
    assert_eq!(after.calls_unresolved, before.calls_unresolved + 1);
    assert_eq!(after.unresolved_attribute, before.unresolved_attribute + 1);
}

#[test]
fn unreadable_file_has_no_row() {
    let found = crate::survey::targets::tests::surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/broken.py", "def broken(:\n"),
    ]);
    assert_eq!(found.coverage.selected_files.len(), 2);
    assert_eq!(found.coverage.measures.unwrap().len(), 1);
    assert_eq!(found.coverage.files_parsed, 1);
}

#[test]
fn each_call_class_has_one_count() {
    let found = crate::survey::targets::tests::surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/one.py", "def make():\n    pass\n"),
        (
            "src/app/two.py",
            "import app.one as mod\nfrom app.one import make\nimport json\ndef f(value):\n    make()\n    mod.make()\n    json.dumps({})\n    len(value)\n    value.method()\n    self.method()\n    value[0]()\n    factory()()\n",
        ),
    ]);
    let row = measured(&found, "app.two");
    assert_eq!(
        (
            row.calls_total,
            row.calls_resolved,
            row.calls_external,
            row.calls_builtin
        ),
        (9, 2, 1, 1)
    );
    assert_eq!(
        (
            row.calls_unresolved,
            row.unresolved_self,
            row.unresolved_attribute,
            row.unresolved_name,
            row.unresolved_dynamic
        ),
        (5, 1, 1, 1, 2)
    );
}

#[test]
fn a_partial_construction_keeps_its_own_class() {
    let found = crate::survey::targets::tests::surveyed(&[
        ("src/app/__init__.py", ""),
        (
            "src/app/one.py",
            "class C:\n    def __new__(cls):\n        pass\ndef f():\n    return C()\n",
        ),
    ]);
    let row = measured(&found, "app.one");
    assert_eq!((row.calls_total, row.calls_partial), (1, 1));
}

#[test]
fn a_proven_dead_site_does_not_gain_an_import_proof() {
    let found = crate::survey::targets::tests::surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/one.py", "def make():\n    pass\n"),
        (
            "src/app/two.py",
            "from app.one import make\nimport app.one as mod\ndef f():\n    if False:\n        make()\n        mod.make()\n        len([])\n",
        ),
    ]);
    let row = measured(&found, "app.two");
    assert_eq!((row.calls_resolved, row.calls_unresolved), (0, 3));
}
