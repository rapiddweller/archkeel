// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reading of one module for its definition table: the text of an expression, the value of a
//! string and the evidence of a node.

use ruff_python_ast::{Expr, ExprStringLiteral};
use ruff_text_size::Ranged;

use crate::survey::module::{EvidenceMap, Module};
use crate::unparse::{self, Failure};

/// The reading of one module: its text, the interpreter and the evidence of the run.
pub struct Scan<'m> {
    pub module: &'m Module,
    pub minor: u32,
    pub evidence_map: &'m mut EvidenceMap,
}

impl Scan<'_> {
    /// `annotation_text`.
    pub fn text(&self, expr: Option<&Expr>) -> Result<Option<String>, Failure> {
        unparse::annotation_text(expr, self.minor, self.module.text())
    }

    /// The value of a string literal; ruff changed a surrogate escape (`Failure::Unseen`).
    pub fn string(&self, node: &ExprStringLiteral) -> Result<String, Failure> {
        let value = node.value.to_str();
        let source = self
            .module
            .text()
            .get(node.range().to_std_range())
            .unwrap_or("");
        if value.contains('\u{fffd}') && source.contains('\\') {
            return Err(Failure::Unseen);
        }
        Ok(value.to_owned())
    }

    /// `add_evidence`.
    pub fn evidence(&mut self, node: &impl Ranged) -> String {
        self.module.evidence(self.evidence_map, node)
    }
}
