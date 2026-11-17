// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The binding of a directive by its combinators, and the libraries that publish (AD-749).

use archkeel_facts::data::ImportData;

use super::{published, Binding};
use crate::syntax::{Combinator, Directive, DirectiveKind, Span};

fn directive(combinators: &[(Combinator, &[&str])]) -> Directive {
    let span = Span {
        line: 1,
        end_line: 1,
        column: 0,
        excerpt: String::new(),
        start_byte: 0,
        end_byte: 0,
    };
    let mut directive = Directive::new(DirectiveKind::Import, span, Some("m.dart".to_owned()));
    directive.combinators = combinators
        .iter()
        .map(|(mode, names)| (*mode, names.iter().map(|name| (*name).to_owned()).collect()))
        .collect();
    directive
}

fn names(list: &[&str]) -> Binding {
    Binding::Names(list.iter().map(|name| (*name).to_owned()).collect())
}

#[test]
fn the_combinators_apply_in_their_order() {
    use Combinator::{Hide, Show};
    assert_eq!(Binding::of(&directive(&[])), Binding::Namespace);
    assert_eq!(
        Binding::of(&directive(&[(Hide, &["A"])])),
        Binding::Namespace
    );
    assert_eq!(
        Binding::of(&directive(&[(Show, &["B", "A"])])),
        names(&["A", "B"])
    );
    // `show` after `hide` keeps no hidden name; `hide` after `show` removes its names.
    assert_eq!(
        Binding::of(&directive(&[(Hide, &["A"]), (Show, &["A", "B"])])),
        names(&["B"])
    );
    assert_eq!(
        Binding::of(&directive(&[(Show, &["A", "B"]), (Hide, &["A"])])),
        names(&["B"])
    );
    assert_eq!(
        Binding::of(&directive(&[(Show, &["A", "B"]), (Show, &["B", "C"])])),
        names(&["B"])
    );
    assert_eq!(
        Binding::of(&directive(&[(Show, &["A"]), (Hide, &["A"])])),
        Binding::Namespace
    );
}

#[test]
fn a_named_record_has_its_first_hop_and_an_open_route_through_an_export() {
    let binding = names(&["Public"]);
    let mut open = ImportData::statement();
    binding.state(&mut open, Some("Public"), "shop.domain.model", false);
    assert_eq!(open.symbol.as_deref(), Some("Public"));
    assert!(open.symbols_known);
    assert_eq!(
        open.reexport_chain,
        Some(vec!["shop.domain.model.Public".to_owned()])
    );
    assert_eq!(open.route_complete, Some(false));
    let mut closed = ImportData::statement();
    binding.state(&mut closed, Some("Public"), "shop.domain.model", true);
    assert_eq!(closed.route_complete, None);
}

#[test]
fn a_namespace_has_no_name_and_states_its_route() {
    let mut whole = ImportData::statement();
    Binding::Namespace.state(&mut whole, None, "shop.domain.model", true);
    assert!(!whole.symbols_known && whole.symbol.is_none() && whole.reexport_chain.is_none());
    assert_eq!(whole.route_complete, None);
    let mut open = ImportData::statement();
    Binding::Namespace.state(&mut open, None, "shop.domain.model", false);
    assert_eq!(open.route_complete, Some(false));
}

#[test]
fn only_a_library_below_lib_and_outside_lib_src_publishes() {
    assert!(published("lib/shop.dart"));
    assert!(published("lib/domain/domain.dart"));
    assert!(!published("lib/src/domain.dart"));
    assert!(!published("test/domain_test.dart"));
    assert!(!published("bin/main.dart"));
    assert!(published("lib/srcs/x.dart"));
}
