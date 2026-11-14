// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reading of one module for its declarations (AD-377, AD-514): the text of an expression, the value of a
//! string and the evidence of a node.

use ruff_python_ast::Expr;
#[cfg(any(test, feature = "dump"))]
use ruff_python_ast::ExprStringLiteral;
use ruff_text_size::Ranged;

use crate::module::{EvidenceMap, Module};
use crate::unparse::{self, TextFailure as Failure};

/// The reading of one module: its text, the interpreter and the evidence of the run.
pub(crate) struct Scan<'m> {
    pub module: &'m Module,
    pub minor: archkeel_facts::pyminor::PyMinor,
    pub evidence_map: &'m mut EvidenceMap,
}

impl Scan<'_> {
    /// `annotation_text`.
    pub(crate) fn text(&self, expr: Option<&Expr>) -> Result<Option<String>, Failure> {
        unparse::annotation_text(expr, self.minor, self.module.text())
    }

    /// The value of a string literal; ruff changed a surrogate escape (`Failure::Unseen`).
    #[cfg(any(test, feature = "dump"))]
    pub(crate) fn string(&self, node: &ExprStringLiteral) -> Result<String, Failure> {
        let value = node.value.to_str();
        let source = self
            .module
            .text()
            .get(node.range().to_std_range())
            .unwrap_or("");
        if unparse::replaced(value, source) {
            return Err(Failure::Unseen);
        }
        Ok(value.to_owned())
    }

    /// `add_evidence`.
    pub(crate) fn evidence(&mut self, node: &impl Ranged) -> String {
        self.module.evidence(self.evidence_map, node)
    }
}
