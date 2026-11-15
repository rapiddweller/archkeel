// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reading of one module for its declarations (AD-518): the evidence of a node, and the text
//! of an annotation or a default.
//!
//! The text is written for a name, a dotted name, `None`, `True` and `False` only. That is what
//! `ast.unparse` writes for them in every Python of the request. Any other expression (a
//! subscript, a string, a number, a call) gives `Unwritable`, and the declaration that holds it
//! gets no record: the survey never guesses a text.

use ruff_python_ast::Expr;
use ruff_text_size::Ranged;

use crate::module::{EvidenceMap, Module};
use crate::survey::binders::Binders;

/// An expression whose text this reader does not write.
#[derive(Debug, PartialEq, Eq)]
pub(super) struct Unwritable;

pub(super) struct Reader<'m> {
    pub module: &'m Module,
    pub evidence_map: &'m mut EvidenceMap,
    /// The builtin type names that the module binds somewhere: their text names something else.
    pub shadowed: Vec<&'static str>,
}

/// The builtin names that an annotation or a default reads as a type or a value.
const BUILTINS: [&str; 18] = [
    "int",
    "str",
    "float",
    "bool",
    "bytes",
    "bytearray",
    "complex",
    "list",
    "dict",
    "set",
    "frozenset",
    "tuple",
    "object",
    "type",
    "range",
    "slice",
    "memoryview",
    "property",
];

impl Reader<'_> {
    /// The builtin names that `binders` shows bound in the module.
    pub(super) fn shadowed(binders: &Binders) -> Vec<&'static str> {
        let hidden = |name: &&str| !binders.builtin_visible(name);
        BUILTINS.iter().copied().filter(hidden).collect()
    }
}

impl Reader<'_> {
    /// The text of an optional expression.
    pub(super) fn text(&self, expr: Option<&Expr>) -> Result<Option<String>, Unwritable> {
        expr.map(|expr| plain(expr, &self.shadowed)).transpose()
    }

    /// `add_evidence`.
    pub(super) fn evidence(&mut self, node: &impl Ranged) -> String {
        self.module.evidence(self.evidence_map, node)
    }
}

fn plain(expr: &Expr, shadowed: &[&str]) -> Result<String, Unwritable> {
    match expr {
        Expr::Name(node) if shadowed.contains(&node.id.as_str()) => Err(Unwritable),
        Expr::Name(node) => Ok(node.id.to_string()),
        Expr::Attribute(node) => Ok(format!(
            "{}.{}",
            plain(&node.value, shadowed)?,
            node.attr.as_str()
        )),
        Expr::NoneLiteral(_) => Ok("None".to_owned()),
        Expr::BooleanLiteral(node) => Ok(if node.value { "True" } else { "False" }.to_owned()),
        _ => Err(Unwritable),
    }
}
