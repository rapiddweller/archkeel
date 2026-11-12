// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn a_parenthesized_boolean_star_is_not_the_yield_grammar_hole() {
    for source in ["x = [*(a or b)]", "f(*(entry.get('ids') or []))"] {
        let tree = crate::test_tree(source, 12).unwrap();
        let reason = check(&tree, source, crate::test_minor(12));
        assert_eq!(reason, None, "{source}");
    }
    assert!(crate::parse::parse(
        "def f():\n    x = [1, *(yield) or b]",
        crate::test_minor(12)
    )
    .is_err());
}

#[test]
fn a_scope_scan_cannot_silently_omit_a_deep_yield() {
    let source = format!(
        "async def f():\n    x = (yield 1){}\n    return 1",
        ".a".repeat(250)
    );
    assert!(crate::parse::parse(&source, crate::test_minor(12)).is_err());
}

#[test]
fn lambda_defaults_evaluate_in_the_outer_scope() {
    assert!(crate::parse::parse("x = lambda a=(yield): a", crate::test_minor(12)).is_err());
}
