// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What an attribute on a `mod` or a `use` item can hide from the scan.
//!
//! A `cfg` can remove a module, a `cfg_attr` can add a `path`, and an attribute macro can rewrite
//! the module. The scan cannot prove an edge across such an item, so it says UNKNOWN.
//! A `cfg(test)` and a `cfg(feature = "x")` of a declared feature are the exceptions: the scan
//! reads the item as if the condition were true, so its edges are the union over all features.

use std::collections::BTreeSet;

use syn::{Attribute, Expr, ExprLit, Lit, Meta};

use crate::tokens::{first_name, split_commas};

/// Attributes that a module can carry without a change to its content.
const MODULE_ATTRIBUTES: [&str; 10] = [
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
];
/// Tool attributes: `clippy::x` and `rustfmt::skip` change no module.
const TOOLS: [&str; 3] = ["clippy", "rustfmt", "rustdoc"];

/// The first reason that an attribute list hides something, or `None`.
pub fn hidden_by(attrs: &[Attribute], what: &str, features: &BTreeSet<String>) -> Option<String> {
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

/// `test`, or `feature = "x"` of a feature that the manifest declares.
fn cfg_is_read(condition: &str, features: &BTreeSet<String>) -> bool {
    let compact: String = condition.split_whitespace().collect();
    compact == "test"
        || compact
            .strip_prefix("feature=\"")
            .and_then(|rest| rest.strip_suffix('"'))
            .is_some_and(|feature| features.contains(feature))
}

/// The literal of `#[path = "x.rs"]`; `Err` when the attribute has no string literal.
pub fn path_literal(attrs: &[Attribute]) -> Result<Option<String>, String> {
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
