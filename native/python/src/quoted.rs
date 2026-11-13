// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Reuse the bounded module preflight before parsing a quoted expression.

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::Expr;

pub(crate) fn expression(text: &str, minor: PyMinor) -> Option<Expr> {
    super::parse(text, minor).ok()?;
    ruff_python_parser::parse_expression(text).ok().map(|n| *n.into_syntax().body)
}
