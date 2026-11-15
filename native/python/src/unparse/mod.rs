// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `ast.unparse` of one expression, as `_Unparser` of the Python in the request writes it, and
//! `source.annotation_text` (AD-377).
//!
//! The Python unparser recurses once for each nested expression and stops with `RecursionError`
//! from about 158 levels (a dict), and the Python collector does not catch it. This writer stops
//! at `MAX_DEPTH` levels with `Failure::Deep`, so it never needs more stack than the parse.

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::Expr;

mod expr;
mod ftext;
mod hazard;
pub(crate) mod literal;
mod outcome;
mod writer;

pub(crate) use hazard::{replaced, string_failure};
use outcome::Prec;
pub(crate) use outcome::TextFailure;
use outcome::TextFailure as Failure;
use writer::Writer;

/// The deepest expression that this writer writes: at most 7 Python frames for each level stay
/// well under the recursion limit of 1 000.
pub(crate) const MAX_DEPTH: u32 = 100;

/// `ast.unparse(expr)` in the Python of `minor`. `source` is the text of the module after
/// `source::newlines`.
pub(crate) fn unparse(expr: &Expr, minor: PyMinor, source: &str) -> Result<String, Failure> {
    let mut writer = Writer::new(minor, source, false);
    writer.expr(expr, Prec::Test)?;
    Ok(writer.out)
}

/// `annotation_text`: the name of a `Name`, `None` without an expression or for `ValueError`.
pub(crate) fn annotation_text(
    expr: Option<&Expr>,
    minor: PyMinor,
    source: &str,
) -> Result<Option<String>, Failure> {
    let Some(expr) = expr else {
        return Ok(None);
    };
    if let Expr::Name(name) = expr {
        return Ok(Some(name.id.to_string()));
    }
    match unparse(expr, minor, source) {
        Ok(text) => Ok(Some(text)),
        Err(Failure::Invalid) => Ok(None),
        Err(failure) => Err(failure),
    }
}

#[cfg(test)]
#[path = "unparse_tests.rs"]
mod tests;
