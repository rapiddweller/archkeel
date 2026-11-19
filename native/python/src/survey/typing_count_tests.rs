// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::count;
use crate::survey::binders::Binders;

#[test]
fn counts_missing_public_positions_and_written_untyped_annotations() {
    let module = crate::test_module(
        "def public(a, b: object) -> Any:\n    pass\ndef _private(x):\n    pass\n",
        11,
    );
    let binders = Binders::of(&module.tree);
    assert_eq!(count(&module, &binders).0, 3);
}

#[test]
fn counts_each_dynamic_call_and_the_private_access() {
    let module = crate::test_module("from typing import cast\ndef f(a: int) -> int:\n    getattr(a, 'x')\n    eval('1')\n    exec('x=1')\n    cast(int, a)\n    return a._hidden\n", 11);
    let binders = Binders::of(&module.tree);
    assert_eq!(count(&module, &binders), (4, 1));
}

#[test]
fn augmented_assignment_reads_the_private_attribute() {
    let module = crate::test_module("def f(a):\n    a._value += 1\n", 11);
    let binders = Binders::of(&module.tree);
    assert_eq!(count(&module, &binders).1, 1);
}

#[test]
fn a_plain_typing_module_import_identifies_cast() {
    let module = crate::test_module(
        "import typing as t\ndef f() -> int:\n    return t.cast(int, 1)\n",
        11,
    );
    let binders = Binders::of(&module.tree);
    assert_eq!(count(&module, &binders).0, 1);
}

#[test]
fn quoted_builtin_and_any_annotations_are_untyped() {
    let module = crate::test_module("def f(x: 'object') -> 'typing.Any':\n    pass\n", 11);
    let binders = Binders::of(&module.tree);
    assert_eq!(count(&module, &binders).0, 2);
}
