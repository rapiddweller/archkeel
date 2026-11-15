// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state of the writer and the leaf writers that call no other writer: the names, the strings
//! and the numbers. The expression writer and the f-string writer build on it.

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::Number;

use super::literal;
use super::outcome::TextFailure as Failure;

pub(super) struct Writer<'s> {
    pub(super) out: String,
    pub(super) minor: PyMinor,
    pub(super) source: &'s str,
    /// 3.11 only: the unparser of a field of an f-string avoids backslashes.
    pub(super) avoid_backslashes: bool,
    pub(super) depth: u32,
}

impl<'s> Writer<'s> {
    pub(super) fn new(minor: PyMinor, source: &'s str, avoid_backslashes: bool) -> Self {
        Writer {
            out: String::new(),
            minor,
            source,
            avoid_backslashes,
            depth: 0,
        }
    }

    /// A writer for a field of an f-string, one level deeper than this one.
    pub(super) fn inner(&self) -> Writer<'s> {
        let mut writer = Writer::new(self.minor, self.source, legacy(self.minor));
        writer.depth = self.depth;
        writer
    }

    pub(super) fn write(&mut self, text: &str) {
        self.out.push_str(text);
    }

    pub(super) fn string(
        &mut self,
        node: &ruff_python_ast::ExprStringLiteral,
    ) -> Result<(), Failure> {
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

    pub(super) fn number(&mut self, number: &Number) -> Result<(), Failure> {
        let text = match number {
            Number::Int(int) => literal::repr_int(&int.to_string()).ok_or(Failure::Invalid)?,
            Number::Float(value) => literal::repr_float(*value, true),
            Number::Complex { imag, .. } => literal::repr_complex(*imag),
        };
        self.write(&text);
        Ok(())
    }
}

pub(super) fn legacy(minor: PyMinor) -> bool {
    match minor {
        PyMinor::Py311 => true,
        PyMinor::Py312 | PyMinor::Py313 | PyMinor::Py314 => false,
    }
}
