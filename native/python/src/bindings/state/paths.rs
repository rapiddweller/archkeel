// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Source paths and mutation names shared by class state and function events.

use ruff_python_ast::Expr;

use crate::bindings::scan::{Result, Scan};
use crate::module::Module;

pub(super) fn mutating(name: &str) -> bool {
    matches!(
        name,
        "add"
            | "append"
            | "clear"
            | "discard"
            | "extend"
            | "insert"
            | "pop"
            | "popitem"
            | "remove"
            | "reverse"
            | "setdefault"
            | "sort"
            | "update"
    )
}

pub(super) fn text(
    scan: &mut Scan,
    module: &Module,
    node: Option<&Expr>,
) -> Result<Option<String>> {
    node.map(|n| crate::bindings::class::text(scan, n, module.text()))
        .transpose()
        .map(Option::flatten)
}

pub(super) fn attribute_path<'a>(
    scan: &mut Scan,
    expr: &'a Expr,
) -> Result<Option<(&'a str, Vec<&'a str>)>> {
    let mut expr = expr;
    let mut parts = Vec::new();
    while let Expr::Attribute(n) = expr {
        scan.tick(1)?;
        parts.push(n.attr.as_str());
        expr = &n.value;
    }
    let Expr::Name(n) = expr else { return Ok(None) };
    scan.tick(parts.len())?;
    parts.reverse();
    Ok(Some((n.id.as_str(), parts)))
}
