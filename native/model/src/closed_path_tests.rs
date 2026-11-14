// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the cycle path (AD-484).

use super::*;

fn names(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| (*item).to_owned()).collect()
}

fn links(items: &[(usize, &str, &str)]) -> Vec<Link> {
    items
        .iter()
        .map(|(index, a, b)| (*index, (*a).to_owned(), (*b).to_owned()))
        .collect()
}

fn path(steps: &[Step]) -> Vec<String> {
    let mut found: Vec<String> = steps.iter().map(|step| step.from.clone()).collect();
    found.extend(steps.last().map(|step| step.to.clone()));
    found
}

#[test]
fn a_path_closes_at_the_first_member_and_takes_the_shortest_way() {
    let members = names(&["a", "b", "c", "d"]);
    let found = cycle_path(
        &members,
        &links(&[
            (0, "a", "b"),
            (1, "b", "c"),
            (2, "c", "d"),
            (3, "d", "a"),
            (4, "c", "a"),
            (5, "b", "d"),
        ]),
    );
    // a -> b -> c -> a (3 steps) is shorter than a -> b -> c -> d -> a.
    assert_eq!(path(&found), ["a", "b", "c", "a"]);
    assert_eq!(found[2].imports, [4]);
}

#[test]
fn each_import_of_a_step_is_listed_and_the_order_does_not_change_the_path() {
    let members = names(&["a", "b"]);
    let forward = links(&[(3, "a", "b"), (1, "a", "b"), (2, "b", "a")]);
    let mut backward = forward.clone();
    backward.reverse();
    let first = cycle_path(&members, &forward);
    assert_eq!(first, cycle_path(&members, &backward));
    assert_eq!(first[0].imports, [1, 3]);
    assert_eq!(path(&first), ["a", "b", "a"]);
}

#[test]
fn a_tie_goes_to_the_smaller_name_and_a_set_without_a_closed_path_has_none() {
    let tie = cycle_path(
        &names(&["a", "b", "c"]),
        &links(&[(0, "a", "c"), (1, "a", "b"), (2, "b", "a"), (3, "c", "a")]),
    );
    assert_eq!(path(&tie), ["a", "b", "a"]);
    assert!(cycle_path(&names(&["a", "b"]), &links(&[(0, "a", "b")])).is_empty());
    assert!(cycle_path(&[], &[]).is_empty());
    assert!(cycle_path(&names(&["a"]), &links(&[(0, "a", "a")])).is_empty());
}
