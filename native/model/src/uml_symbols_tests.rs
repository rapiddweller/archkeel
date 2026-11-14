// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The base receipt of a class (`_coverage` of release 4.0.1): a missing base is FAIL only when
//! each base of the class, and of each class inside it, resolves (AD-512).

use archkeel_contract::EntityKind;

use super::bases_complete;
use crate::symbols::{Entity, Symbols};

/// A table with the class `outer` and the class `inner` inside it, with their base receipts.
fn table(outer: bool, inner: bool) -> Symbols {
    let mut table = Symbols::default();
    let class = |id: &str, parent: Option<&str>| {
        let mut entity = Entity::named(id.to_owned(), EntityKind::Class, id, Vec::new());
        entity.parent = parent.map(str::to_owned);
        entity
    };
    table.push(class("outer", None));
    table.push(class("inner", Some("outer")));
    table.bases.insert("outer".to_owned(), outer);
    table.bases.insert("inner".to_owned(), inner);
    table
}

#[test]
fn a_class_with_resolved_bases_and_resolved_inner_classes_has_the_receipt() {
    assert!(bases_complete(&table(true, true), "outer"));
}

#[test]
fn an_unresolved_base_of_the_class_or_of_a_class_inside_it_takes_the_receipt() {
    assert!(!bases_complete(&table(false, true), "outer"));
    assert!(!bases_complete(&table(true, false), "outer"));
}

#[test]
fn an_unresolved_base_of_a_class_that_does_not_lie_inside_the_class_does_not_take_it() {
    assert!(!bases_complete(&table(true, false), "inner"));
    let mut other = table(true, true);
    other.bases.insert("elsewhere".to_owned(), false);
    assert!(bases_complete(&other, "outer"));
}

#[test]
fn a_class_without_a_receipt_has_none() {
    assert!(!bases_complete(&Symbols::default(), "outer"));
}
