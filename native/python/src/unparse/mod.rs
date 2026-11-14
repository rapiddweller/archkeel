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
use ruff_python_ast::{Expr, Number, Parameters};

mod ftext;
mod hazard;
pub(crate) mod literal;
mod operators;
mod outcome;

pub(crate) use hazard::{replaced, string_failure};
use outcome::Prec;
pub(crate) use outcome::TextFailure;
use outcome::TextFailure as Failure;

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

struct Writer<'s> {
    out: String,
    minor: PyMinor,
    source: &'s str,
    /// 3.11 only: the unparser of a field of an f-string avoids backslashes.
    avoid_backslashes: bool,
    depth: u32,
}

impl<'s> Writer<'s> {
    fn new(minor: PyMinor, source: &'s str, avoid_backslashes: bool) -> Self {
        Writer {
            out: String::new(),
            minor,
            source,
            avoid_backslashes,
            depth: 0,
        }
    }

    /// A writer for a field of an f-string, one level deeper than this one.
    fn inner(&self) -> Writer<'s> {
        let mut writer = Writer::new(self.minor, self.source, legacy(self.minor));
        writer.depth = self.depth;
        writer
    }

    fn write(&mut self, text: &str) {
        self.out.push_str(text);
    }

    /// `traverse` of an expression whose parent set the precedence `prec`.
    fn expr(&mut self, expr: &Expr, prec: Prec) -> Result<(), Failure> {
        self.depth += 1;
        if self.depth > MAX_DEPTH {
            return Err(Failure::Deep);
        }
        let result = self.dispatch(expr, prec);
        self.depth -= 1;
        result
    }

    fn dispatch(&mut self, expr: &Expr, prec: Prec) -> Result<(), Failure> {
        if let Some(failure) = string_failure(expr, self.source, self.minor) {
            return Err(failure);
        }
        match expr {
            Expr::Name(node) => self.write(node.id.as_str()),
            Expr::StringLiteral(node) => self.string(node)?,
            Expr::BytesLiteral(node) => {
                let bytes: Vec<u8> = node.value.bytes().collect();
                self.write(&literal::repr_bytes(&bytes));
            }
            Expr::NumberLiteral(node) => self.number(&node.value)?,
            Expr::BooleanLiteral(node) => self.write(if node.value { "True" } else { "False" }),
            Expr::NoneLiteral(_) => self.write("None"),
            Expr::EllipsisLiteral(_) => self.write("..."),
            Expr::FString(node) => {
                let pieces = crate::pyast::fstring::fstring(&node.value);
                self.ftext(&pieces, "f")?;
            }
            Expr::TString(node) => {
                let pieces = crate::pyast::fstring::tstring(&node.value);
                self.ftext(&pieces, "t")?;
            }
            Expr::IpyEscapeCommand(_) => return Err(Failure::Invalid),
            _ => self.compound(expr, prec)?,
        }
        Ok(())
    }

    fn string(&mut self, node: &ruff_python_ast::ExprStringLiteral) -> Result<(), Failure> {
        let value = node.value.to_str();
        if node.value.is_unicode() {
            self.write("u");
        }
        let text = if self.avoid_backslashes {
            literal::avoiding_backslashes(value, &literal::ALL_QUOTES, self.minor)
        } else {
            literal::repr_str(value, self.minor)
        };
        self.write(&text);
        Ok(())
    }

    fn number(&mut self, number: &Number) -> Result<(), Failure> {
        let text = match number {
            Number::Int(int) => literal::repr_int(&int.to_string()).ok_or(Failure::Invalid)?,
            Number::Float(value) => literal::repr_float(*value, true),
            Number::Complex { imag, .. } => literal::repr_complex(*imag),
        };
        self.write(&text);
        Ok(())
    }

    /// `interleave(", ", traverse, items)` with the default precedence.
    fn items(&mut self, items: &[Expr]) -> Result<(), Failure> {
        for (index, item) in items.iter().enumerate() {
            if index > 0 {
                self.write(", ");
            }
            self.expr(item, Prec::Test)?;
        }
        Ok(())
    }

    /// `items_view`: one item takes a trailing comma.
    fn items_view(&mut self, items: &[Expr]) -> Result<(), Failure> {
        if let [item] = items {
            self.expr(item, Prec::Test)?;
            self.write(",");
            Ok(())
        } else {
            self.items(items)
        }
    }

    /// `visit_arguments`.
    fn arguments(&mut self, params: &Parameters) -> Result<(), Failure> {
        let mut first = true;
        let positional = params.posonlyargs.len();
        for (index, param) in params.posonlyargs.iter().chain(&params.args).enumerate() {
            if !first {
                self.write(", ");
            }
            first = false;
            self.arg(&param.parameter)?;
            if let Some(default) = &param.default {
                self.write("=");
                self.expr(default, Prec::Test)?;
            }
            if index + 1 == positional {
                self.write(", /");
            }
        }
        if params.vararg.is_some() || !params.kwonlyargs.is_empty() {
            if !first {
                self.write(", ");
            }
            first = false;
            self.write("*");
            if let Some(vararg) = &params.vararg {
                self.arg(vararg)?;
            }
        }
        for param in &params.kwonlyargs {
            self.write(", ");
            self.arg(&param.parameter)?;
            if let Some(default) = &param.default {
                self.write("=");
                self.expr(default, Prec::Test)?;
            }
        }
        if let Some(kwarg) = &params.kwarg {
            if !first {
                self.write(", ");
            }
            self.write("**");
            self.arg(kwarg)?;
        }
        Ok(())
    }

    /// `visit_arg`: the name and its annotation.
    fn arg(&mut self, param: &ruff_python_ast::Parameter) -> Result<(), Failure> {
        self.write(param.name.as_str());
        if let Some(annotation) = &param.annotation {
            self.write(": ");
            self.expr(annotation, Prec::Test)?;
        }
        Ok(())
    }
}

fn legacy(minor: PyMinor) -> bool {
    match minor {
        PyMinor::Py311 => true,
        PyMinor::Py312 | PyMinor::Py313 | PyMinor::Py314 => false,
    }
}

#[cfg(test)]
#[path = "unparse_tests.rs"]
mod tests;
