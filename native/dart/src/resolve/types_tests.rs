// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type texts of the resolver, as release 4.0.1 reads them (`resolve.py`).

use super::{key, names, nominal, split, substitute, type_name};

#[test]
fn a_nominal_type_is_a_name_with_an_optional_prefix() {
    assert_eq!(nominal("Order"), Some((None, "Order")));
    assert_eq!(nominal(" p.Order "), Some((Some("p"), "Order")));
    assert_eq!(nominal("List<Map<String, int>>"), Some((None, "List")));
    assert_eq!(nominal("List<int"), None);
    assert_eq!(nominal("a.b.C"), None);
    assert_eq!(nominal("Order?"), None);
    assert_eq!(nominal("void Function()"), None);
}

#[test]
fn a_substitution_replaces_whole_words_only() {
    let map = [("T".to_owned(), "Order".to_owned())];
    assert_eq!(
        substitute(Some("List<T>"), &map).as_deref(),
        Some("List<Order>")
    );
    assert_eq!(
        substitute(Some("Type T TT _T T1"), &map).as_deref(),
        Some("Type Order TT _T T1")
    );
    assert_eq!(substitute(None, &map), None);
}

#[test]
fn the_helpers_read_names_arguments_and_keys() {
    assert_eq!(type_name("  Order<int>"), Some("Order"));
    assert_eq!(type_name("<int>"), None);
    assert_eq!(
        names("Map<String, List<p.T>>?"),
        ["Map", "String", "List", "p", "T"]
    );
    assert_eq!(
        split("int, Map<String, int>, T"),
        ["int", "Map<String, int>", "T"]
    );
    assert_eq!(key("Map< String ,int >"), "Map<String,int>");
}
