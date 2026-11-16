// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::collections::{BTreeMap, BTreeSet};

use super::{requires, Require};

fn pair(source: &str, target: &str) -> (String, String) {
    (source.to_owned(), target.to_owned())
}

fn row(source: &str, target: &str, imports: usize) -> Require {
    Require {
        source: source.to_owned(),
        target: target.to_owned(),
        imports,
    }
}

#[test]
fn a_declared_pair_counts_the_observed_imports_and_an_unused_pair_counts_zero() {
    let pairs = BTreeSet::from([pair("api", "core"), pair("api", "store")]);
    let observed = [("api", "core", 3), ("core", "api", 7)];
    let rows = requires(pairs, &BTreeMap::new(), observed.into_iter());
    assert_eq!(rows, [row("api", "core", 3), row("api", "store", 0)]);
}

#[test]
fn an_import_of_a_sub_component_counts_for_the_pair_of_its_parent() {
    let parents = BTreeMap::from([("api.http", "api"), ("api.cli", "api")]);
    let pairs = BTreeSet::from([pair("api", "core"), pair("api.http", "api.cli")]);
    let observed = [
        ("api.http", "core", 2),
        ("api.cli", "core", 1),
        ("api.http", "api.cli", 4),
    ];
    let rows = requires(pairs, &parents, observed.into_iter());
    // An import inside `api` is no import from `api` to `api`.
    assert_eq!(rows, [row("api", "core", 3), row("api.http", "api.cli", 4)]);
}
