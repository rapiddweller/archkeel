// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that the call of an `eval` or `exec` site hands to the code that it runs (#2239).
//!
//! A contract that declares a site as user code claims that this code changes no module of the
//! product. A call that hands the names of the product to it contradicts that claim: the code can
//! write them. The class is a fact about the call, never about the text that it runs.

use archkeel_facts::data::TrojanHorseForm;
use archkeel_facts::vocab::SiteNamespace;
use ruff_python_ast::{Expr, ExprCall};
use ruff_text_size::Ranged;

use super::trojan_horse::Site;

/// Set the class of the names on each `eval` and `exec` site that is the callee of `call`.
/// `builtin_dict` is true when the name `dict` is the builtin: no import, parameter or local binds it.
pub(super) fn attach(sites: &mut [Site], call: &ExprCall, builtin_dict: bool) {
    let callee = call.func.range();
    for site in sites.iter_mut().filter(|site| site.range == callee) {
        if matches!(
            site.trojan_horse,
            Some(TrojanHorseForm::Eval | TrojanHorseForm::Exec)
        ) {
            site.namespace = Some(of(call, builtin_dict));
        }
    }
}

/// The class of the mapping that the call gives the code: its second positional argument or its
/// `globals` keyword. A spread hides the position of every argument: unknown.
fn of(call: &ExprCall, builtin_dict: bool) -> SiteNamespace {
    let keywords = &call.arguments.keywords;
    if keywords.iter().any(|keyword| keyword.arg.is_none())
        || call.arguments.args.iter().any(Expr::is_starred_expr)
    {
        return SiteNamespace::Unknown;
    }
    let named = keywords.iter().find(|keyword| {
        keyword
            .arg
            .as_ref()
            .is_some_and(|name| name.as_str() == "globals")
    });
    match call
        .arguments
        .args
        .get(1)
        .or(named.map(|keyword| &keyword.value))
    {
        None | Some(Expr::NoneLiteral(_)) => SiteNamespace::Default,
        Some(expression) => class(expression, builtin_dict),
    }
}

fn class(expression: &Expr, builtin_dict: bool) -> SiteNamespace {
    match expression {
        Expr::Dict(_) => SiteNamespace::Fresh,
        // `dict(...)` builds a new mapping only when `dict` is the builtin.
        Expr::Call(call) => match &*call.func {
            Expr::Name(name) if name.id.as_str() == "dict" && builtin_dict => SiteNamespace::Fresh,
            func => match called(func) {
                Some("globals" | "locals" | "vars") => SiteNamespace::Shared,
                _ => SiteNamespace::Unknown,
            },
        },
        Expr::Attribute(node) if node.attr.as_str() == "__dict__" => SiteNamespace::Shared,
        Expr::Subscript(node) if is_modules(&node.value) => SiteNamespace::Shared,
        _ => SiteNamespace::Unknown,
    }
}

/// The last name of a callee: `globals`, `builtins.globals`.
fn called(func: &Expr) -> Option<&str> {
    match func {
        Expr::Name(node) => Some(node.id.as_str()),
        Expr::Attribute(node) => Some(node.attr.as_str()),
        _ => None,
    }
}

/// True for `sys.modules` and for `modules` as a name.
fn is_modules(expression: &Expr) -> bool {
    match expression {
        Expr::Name(node) => node.id.as_str() == "modules",
        Expr::Attribute(node) => node.attr.as_str() == "modules",
        _ => false,
    }
}

#[cfg(test)]
#[path = "hazards_namespace_tests.rs"]
mod tests;
