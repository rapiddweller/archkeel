// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The component cycles of a model (slice S7, AD-384). The evaluator tests check the rows over
//! the frozen replies; this test checks the depth of the walk.

use super::super::condensation::condense;

#[test]
fn a_chain_of_many_components_closed_into_one_cycle_is_one_component_without_recursion() {
    let count = 100_000;
    let mut edges: Vec<(usize, usize)> = (0..count - 1).map(|n| (n, n + 1)).collect();
    edges.push((count - 1, 0));
    let found = condense(count, &edges);
    assert_eq!(found.components().len(), 1);
    assert_eq!(found.components()[0].len(), count);
}
