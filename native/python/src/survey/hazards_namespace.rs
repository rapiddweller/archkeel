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
pub(super) fn attach(sites: &mut [Site], call: &ExprCall, class: SiteNamespace) {
    let callee = call.func.range();
    for site in sites.iter_mut().filter(|site| site.range == callee) {
        if matches!(
            site.trojan_horse,
            Some(TrojanHorseForm::Eval | TrojanHorseForm::Exec)
        ) {
            site.namespace = Some(class);
        }
    }
}

/// The class of the names that the call gives the code (`builtin` tells whether a name is the
/// builtin: no import, parameter or local binds it): its globals (second positional argument
/// or `globals=`) and its locals (third or `locals=`). A spread hides the position of every
/// argument: unknown.
pub(super) fn of(call: &ExprCall, builtin: &dyn Fn(&str) -> bool) -> SiteNamespace {
    let keywords = &call.arguments.keywords;
    if keywords.iter().any(|keyword| keyword.arg.is_none())
        || call.arguments.args.iter().any(Expr::is_starred_expr)
    {
        return SiteNamespace::Unknown;
    }
    let given = |position: usize, name: &str| {
        let keyword = keywords
            .iter()
            .find(|keyword| keyword.arg.as_ref().is_some_and(|arg| arg.as_str() == name));
        call.arguments
            .args
            .get(position)
            .or(keyword.map(|keyword| &keyword.value))
    };
    let globals = match given(1, "globals") {
        None | Some(Expr::NoneLiteral(_)) => SiteNamespace::Default,
        Some(expression) => class(expression, builtin),
    };
    let locals = given(2, "locals")
        .filter(|expression| !matches!(expression, Expr::NoneLiteral(_)))
        .map(|expression| class(expression, builtin));
    // The code writes the mapping that is shared or unproved, whichever argument holds it.
    let mappings = [Some(globals), locals];
    let mut seen = mappings.into_iter().flatten();
    let worst = |a: SiteNamespace, b: SiteNamespace| match (a, b) {
        (SiteNamespace::Shared, _) | (_, SiteNamespace::Shared) => SiteNamespace::Shared,
        (SiteNamespace::Default, _) | (_, SiteNamespace::Default) => SiteNamespace::Default,
        (SiteNamespace::Unknown, _) | (_, SiteNamespace::Unknown) => SiteNamespace::Unknown,
        _ => SiteNamespace::Fresh,
    };
    seen.next().map_or(globals, |first| seen.fold(first, worst))
}

fn class(expression: &Expr, builtin: &dyn Fn(&str) -> bool) -> SiteNamespace {
    match expression {
        Expr::Dict(_) => SiteNamespace::Fresh,
        // A helper counts only as the builtin: an import, a parameter or a method of the name is
        // not proved to build, or to return, what the builtin does.
        Expr::Call(call) => match &*call.func {
            Expr::Name(name) if builtin(name.id.as_str()) => match name.id.as_str() {
                "dict" => SiteNamespace::Fresh,
                "globals" | "locals" | "vars" => SiteNamespace::Shared,
                _ => SiteNamespace::Unknown,
            },
            _ => SiteNamespace::Unknown,
        },
        Expr::Attribute(node) if node.attr.as_str() == "__dict__" => SiteNamespace::Shared,
        Expr::Subscript(node) if is_modules(&node.value) => SiteNamespace::Shared,
        _ => SiteNamespace::Unknown,
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
