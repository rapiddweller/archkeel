// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn a_large_target_list_charges_the_loop_as_well_as_each_target() {
    let count = 20_000;
    let source = format!("({}) = values", "x,".repeat(count));
    let tree = crate::test_tree(&source, 12).unwrap();
    let ruff_python_ast::Stmt::Assign(assignment) = &tree.body[0] else {
        assert_eq!(format!("{:?}", tree.body), "an assignment");
        return;
    };
    let Expr::Tuple(tuple) = &assignment.targets[0] else {
        assert_eq!(format!("{:?}", assignment.targets), "a tuple target");
        return;
    };
    let mut work = Work::new();
    assert!(work.charge(super::super::work::MAX_WORK - count));
    assert_eq!(
        targets(&tuple.elts, &mut work, 0),
        Some("CPython validation work limit exceeded")
    );
}

#[test]
fn a_long_boolean_star_charges_each_lexer_step() {
    let count = 20_000;
    let source = format!("*({}a)", "a or ".repeat(count));
    let mut work = Work::new();
    assert!(work.charge(super::super::work::MAX_WORK - count));
    assert!(!grouped_star(&source, &mut work));
    assert_eq!(
        work.failure(),
        Some("CPython validation work limit exceeded")
    );
}
