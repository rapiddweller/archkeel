// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What an attribute on a `mod` or a `use` item can hide from the scan.
//!
//! A `cfg` can remove a module, a `cfg_attr` can add a `path`, and an attribute macro can rewrite
//! the module. The scan cannot prove an edge across such an item, so it says UNKNOWN.
//! A `cfg(test)` and a `cfg(feature = "x")` of a declared feature are the exceptions, also inside
//! `any` and `all`: the scan reads the item as if the condition were true, so its edges
//! are the union over all features.

use std::collections::BTreeSet;

use syn::{Attribute, Expr, ExprLit, ImplItem, Item, Lit, Meta, TraitItem};

use crate::tokens::{first_name, split_commas};

/// Attributes that a module can carry without a change to its content.
const MODULE_ATTRIBUTES: [&str; 11] = [
    "path",
    "allow",
    "warn",
    "deny",
    "forbid",
    "expect",
    "doc",
    "deprecated",
    "must_use",
    "no_implicit_prelude",
    "macro_use",
];
/// Tool attributes: `clippy::x` and `rustfmt::skip` change no module.
const TOOLS: [&str; 3] = ["clippy", "rustfmt", "rustdoc"];

/// The first reason that an attribute list hides something, or `None`.
pub(crate) fn hidden_by(
    attrs: &[Attribute],
    what: &str,
    features: &BTreeSet<String>,
) -> Option<String> {
    attrs.iter().find_map(|attr| reason(attr, what, features))
}

fn reason(attr: &Attribute, what: &str, features: &BTreeSet<String>) -> Option<String> {
    let path = attr.path();
    let name = path.get_ident().map(ToString::to_string);
    match (name.as_deref(), &attr.meta) {
        (Some("cfg"), Meta::List(list)) => {
            let condition = list.tokens.to_string();
            (!cfg_is_read(&condition, features))
                .then(|| format!("A cfg condition gates a {what}: cfg({condition})"))
        }
        (Some("cfg_attr"), Meta::List(list)) => split_commas(list.tokens.clone())
            .iter()
            .skip(1)
            .any(|part| !first_name(part).is_some_and(|name| lint_like(&name)))
            .then(|| format!("A cfg_attr gates a {what}: cfg_attr({})", list.tokens)),
        (Some(name), _) if what == "module" && !MODULE_ATTRIBUTES.contains(&name) => {
            Some(format!("An attribute macro is applied to a module: {name}"))
        }
        (None, _) if what == "module" && !is_tool(path) => {
            Some("An attribute macro is applied to a module: a path attribute".to_owned())
        }
        _ => None,
    }
}

fn is_tool(path: &syn::Path) -> bool {
    path.segments
        .first()
        .is_some_and(|segment| TOOLS.contains(&segment.ident.to_string().as_str()))
}

fn lint_like(name: &str) -> bool {
    matches!(
        name,
        "allow"
            | "warn"
            | "deny"
            | "forbid"
            | "expect"
            | "doc"
            | "must_use"
            | "inline"
            | "deprecated"
    )
}

/// `test`, `feature = "x"` of a declared feature, and `any` and `all` of such conditions. `not` stays UNKNOWN.
/// The scan reads the item as if the condition were true, so a combinator adds no risk when each
/// leaf is one that the scan knows.
fn cfg_is_read(condition: &str, features: &BTreeSet<String>) -> bool {
    let compact: String = condition.split_whitespace().collect();
    known(&compact, features, 0)
}

/// The deepest `any(all(...))` that is read; a deeper condition is UNKNOWN.
const MAX_CFG_DEPTH: usize = 16;

fn known(condition: &str, features: &BTreeSet<String>, depth: usize) -> bool {
    if depth > MAX_CFG_DEPTH {
        return false;
    }
    if condition == "test" {
        return true;
    }
    if let Some(feature) = condition
        .strip_prefix("feature=\"")
        .and_then(|rest| rest.strip_suffix('"'))
    {
        return features.contains(feature);
    }
    ["any(", "all("].iter().any(|open| {
        condition
            .strip_prefix(open)
            .and_then(|rest| rest.strip_suffix(')'))
            .is_some_and(|inside| {
                let parts = top_level_parts(inside);
                !parts.is_empty() && parts.iter().all(|part| known(part, features, depth + 1))
            })
    })
}

/// Split at the commas that are not inside a bracket or a string.
fn top_level_parts(text: &str) -> Vec<&str> {
    let (mut parts, mut start, mut depth, mut quoted) = (Vec::new(), 0, 0_usize, false);
    for (at, character) in text.char_indices() {
        match character {
            '"' => quoted = !quoted,
            '(' if !quoted => depth += 1,
            ')' if !quoted => depth = depth.saturating_sub(1),
            ',' if !quoted && depth == 0 => {
                parts.push(&text[start..at]);
                start = at + 1;
            }
            _ => {}
        }
    }
    let last = &text[start..];
    if !last.is_empty() {
        parts.push(last);
    }
    parts
}

/// Whether rustc builds the item only in a test build: `#[test]`, a test attribute of a crate
/// (`#[tokio::test]`, `#[rstest]`), `#[cfg(test)]` and `#[cfg(all(test, ..))]`. `any(test, x)`, `not(test)` and `cfg_attr(test, ..)` do not count:
/// production code can still build them, so the scan keeps their edges.
pub(crate) fn is_test_attributes(attrs: &[Attribute]) -> bool {
    attrs.iter().any(|attr| match &attr.meta {
        Meta::List(list) if attr.path().is_ident("cfg") => {
            let compact: String = list.tokens.to_string().split_whitespace().collect();
            needs_test(&compact, 0)
        }
        Meta::NameValue(_) => false,
        _ => test_function(attr.path()),
    })
}

/// `test` and `krate::test` (`tokio::test`, `sqlx::test`), also with arguments, and `rstest`.
fn test_function(path: &syn::Path) -> bool {
    path.segments.last().is_some_and(|last| {
        last.ident == "test" || (path.segments.len() == 1 && last.ident == "rstest")
    })
}

fn needs_test(condition: &str, depth: usize) -> bool {
    if depth > MAX_CFG_DEPTH {
        return false;
    }
    condition == "test"
        || condition
            .strip_prefix("all(")
            .and_then(|rest| rest.strip_suffix(')'))
            .is_some_and(|inside| {
                top_level_parts(inside)
                    .iter()
                    .any(|part| needs_test(part, depth + 1))
            })
}

/// The attributes of a member of an `impl` block or a `trait`: their variants have one shape.
macro_rules! member_attributes {
    ($item:expr, $kind:ident) => {
        match $item {
            $kind::Const(item) => &item.attrs,
            $kind::Fn(item) => &item.attrs,
            $kind::Type(item) => &item.attrs,
            $kind::Macro(item) => &item.attrs,
            _ => &[],
        }
    };
}

pub(crate) fn impl_item_attributes(item: &syn::ImplItem) -> &[Attribute] {
    member_attributes!(item, ImplItem)
}

pub(crate) fn trait_item_attributes(item: &syn::TraitItem) -> &[Attribute] {
    member_attributes!(item, TraitItem)
}

/// The attributes of a statement that is no item: a `let` or a macro call.
pub(crate) fn statement_attributes(stmt: &syn::Stmt) -> &[Attribute] {
    match stmt {
        syn::Stmt::Local(local) => &local.attrs,
        syn::Stmt::Macro(mac) => &mac.attrs,
        _ => &[],
    }
}

/// The attributes of an item, whatever its kind.
pub(crate) fn item_attributes(item: &Item) -> &[Attribute] {
    match item {
        Item::Const(item) => &item.attrs,
        Item::Enum(item) => &item.attrs,
        Item::ExternCrate(item) => &item.attrs,
        Item::Fn(item) => &item.attrs,
        Item::ForeignMod(item) => &item.attrs,
        Item::Impl(item) => &item.attrs,
        Item::Macro(item) => &item.attrs,
        Item::Mod(item) => &item.attrs,
        Item::Static(item) => &item.attrs,
        Item::Struct(item) => &item.attrs,
        Item::Trait(item) => &item.attrs,
        Item::TraitAlias(item) => &item.attrs,
        Item::Type(item) => &item.attrs,
        Item::Union(item) => &item.attrs,
        Item::Use(item) => &item.attrs,
        _ => &[],
    }
}

/// The literal of `#[path = "x.rs"]`; `Err` when the attribute has no string literal.
pub(crate) fn path_literal(attrs: &[Attribute]) -> Result<Option<String>, String> {
    let Some(attr) = attrs.iter().find(|attr| attr.path().is_ident("path")) else {
        return Ok(None);
    };
    let Meta::NameValue(pair) = &attr.meta else {
        return Err("A path attribute has no value".to_owned());
    };
    match &pair.value {
        Expr::Lit(ExprLit {
            lit: Lit::Str(text),
            ..
        }) => Ok(Some(text.value())),
        _ => Err("A path attribute is not a string literal".to_owned()),
    }
}

#[cfg(test)]
#[path = "attrs_tests.rs"]
mod tests;
