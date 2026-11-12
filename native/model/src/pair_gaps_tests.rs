// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reading of each rule kind and the gaps that hold it (slice S7, AD-384 point 4).

use super::{Kept, Reads};
use crate::selection::Selection;

fn kept(source: &str, target: &str, observed: bool, owned: [bool; 2], external: bool) -> Kept {
    Kept {
        source: source.to_owned(),
        target: target.to_owned(),
        observed,
        owned,
        target_external: external,
    }
}

const OWNED: [bool; 2] = [true, true];

#[test]
fn a_gap_with_an_end_outside_the_reply_holds_each_reading() {
    let gap = kept("a.x", "b.y", false, OWNED, false);
    for reads in [
        Reads::NoEdge,
        Reads::Modules,
        Reads::ExternalImports,
        Reads::Members(vec!["z"]),
        Reads::Every,
    ] {
        assert!(gap.holds(&reads), "{reads:?}");
    }
}

#[test]
fn a_reading_without_edges_is_never_held_by_a_proven_pair() {
    let gap = kept("a.x", "b.y", true, [false, false], true);
    assert!(!gap.holds(&Reads::NoEdge));
    assert!(!gap.holds(&Reads::Modules));
    assert!(gap.holds(&Reads::Every));
}

#[test]
fn an_external_reading_is_held_only_by_a_gap_into_a_module_with_an_external_import() {
    assert!(kept("a.x", "b.y", true, OWNED, true).holds(&Reads::ExternalImports));
    assert!(!kept("a.x", "b.y", true, OWNED, false).holds(&Reads::ExternalImports));
}

#[test]
fn a_member_reading_is_held_by_a_gap_that_touches_a_member_at_either_end() {
    let members = Reads::Members(vec!["app.m"]);
    assert!(kept("app.m.x", "app.n", true, OWNED, false).holds(&members));
    assert!(kept("app.n", "app.m", true, OWNED, false).holds(&members));
    assert!(!kept("app.n", "app.o", true, OWNED, false).holds(&members));
    assert!(!kept("app.mm", "app.o", true, OWNED, false).holds(&members));
}

#[test]
fn a_side_reading_is_held_when_each_end_matches_its_side_or_has_no_one_owner() {
    let sides = || {
        Reads::Sides([
            Selection::of_packages(vec!["app.domain"]),
            Selection::of_packages(vec!["app.data"]),
        ])
    };
    assert!(kept("app.domain.a", "app.data.b", true, OWNED, false).holds(&sides()));
    assert!(!kept("app.domain.a", "app.ui.b", true, OWNED, false).holds(&sides()));
    assert!(!kept("app.ui.a", "app.data.b", true, OWNED, false).holds(&sides()));
    // The reverse direction is no forbidden edge.
    assert!(!kept("app.data.b", "app.domain.a", true, OWNED, false).holds(&sides()));
    // An end without one owner can be on its side.
    assert!(kept("app.domain.a", "app.ui.b", true, [true, false], false).holds(&sides()));
    assert!(kept("app.ui.a", "app.data.b", true, [false, true], false).holds(&sides()));
}

#[test]
fn the_walk_of_the_cycle_part_reaches_a_node_over_many_steps() {
    use std::collections::BTreeSet;
    let edges: BTreeSet<(&str, &str)> = [("b", "c"), ("c", "d"), ("d", "a"), ("x", "b")].into();
    let found = super::reach(&edges, &["b"].into());
    assert!(found.contains(&("a", "b")), "b reaches a over three steps");
    assert!(!found.contains(&("x", "b")), "b does not reach x");
    // A chain of many nodes needs no recursion.
    let names: Vec<String> = (0..100_000).map(|n| format!("m{n}")).collect();
    let chain: BTreeSet<(&str, &str)> = names
        .windows(2)
        .map(|pair| (pair[0].as_str(), pair[1].as_str()))
        .collect();
    let last = names[names.len() - 1].as_str();
    assert!(super::reach(&chain, &["m0"].into()).contains(&(last, "m0")));
}
