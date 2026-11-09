// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the sites of a file. A scope hides the names of its parameters and of its body, and a
// chain of scopes hides the union.

use super::Names;
use crate::site_paths::Text;

#[test]
fn a_chain_unites_the_names_of_its_scopes_and_sorts_them() {
    //          0         1         2         3
    //          0123456789012345678901234567890123456
    let data = b"function f(b){var a;} function g(c){}";
    let mut names = Names::default();
    names.declared(11, Text { start: 11, end: 12 });
    names.written(14, Text { start: 18, end: 19 });
    names.declared(33, Text { start: 33, end: 34 });
    let outer = names.open(None, Some((10, 13)), Some((13, 21)));
    let inner = names.open(Some(outer), Some((32, 35)), Some((35, 37)));
    assert_eq!(names.shadowed(Some(outer), data), ["a", "b"]);
    assert_eq!(names.shadowed(Some(inner), data), ["a", "b", "c"]);
    assert!(names.shadowed(None, data).is_empty());
}

#[test]
fn a_scope_hides_only_the_names_that_start_inside_its_ranges() {
    let data = b"abcdef";
    let mut names = Names::default();
    names.written(0, Text { start: 0, end: 1 });
    names.written(2, Text { start: 2, end: 3 });
    names.written(4, Text { start: 4, end: 5 });
    let scope = names.open(None, None, Some((2, 4)));
    assert_eq!(names.shadowed(Some(scope), data), ["c"]);
}

#[test]
fn a_name_that_two_scopes_hide_counts_once() {
    let data = b"aa";
    let mut names = Names::default();
    names.written(0, Text { start: 0, end: 1 });
    names.written(1, Text { start: 1, end: 2 });
    let outer = names.open(None, None, Some((0, 2)));
    let inner = names.open(Some(outer), None, Some((1, 2)));
    assert_eq!(names.shadowed(Some(inner), data), ["a"]);
}

#[test]
fn the_index_answers_what_the_union_of_the_chain_holds() {
    let data = b"function f(b){var a;} function g(c){}";
    let mut names = Names::default();
    names.declared(11, Text { start: 11, end: 12 });
    names.written(14, Text { start: 18, end: 19 });
    names.declared(33, Text { start: 33, end: 34 });
    let outer = names.open(None, Some((10, 13)), Some((13, 21)));
    let inner = names.open(Some(outer), Some((32, 35)), Some((35, 37)));
    let index = names.index(data);
    for chain in [None, Some(outer), Some(inner)] {
        let held = names.shadowed(chain, data);
        for name in ["a", "b", "c", "d"] {
            assert_eq!(
                index.shadows(chain, name),
                held.iter().any(|item| item == name),
                "{name}"
            );
        }
    }
}
