// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Comprehension target scope for the import hazard survey.

use std::collections::HashSet;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Comprehension, Expr, ExprContext};

/// The first generator, later generators, local names and result expressions.
type Parts<'a> = (
    &'a Comprehension,
    &'a [Comprehension],
    HashSet<String>,
    Vec<&'a Expr>,
);

/// The comprehension parts and its local targets; the first iterable has the enclosing scope.
pub(super) fn parts(expr: &Expr) -> Option<Parts<'_>> {
    let generators: &[Comprehension] = match expr {
        Expr::Generator(node) => &node.generators,
        Expr::DictComp(node) => &node.generators,
        Expr::SetComp(node) => &node.generators,
        Expr::ListComp(node) => &node.generators,
        _ => return None,
    };
    let (first, rest) = generators.split_first()?;
    let mut targets = Targets::default();
    for generator in generators {
        targets.visit_expr(&generator.target);
    }
    let mut values = Vec::new();
    match expr {
        Expr::Generator(node) => values.push(node.elt.as_ref()),
        Expr::DictComp(node) => {
            values.extend(node.key.as_deref());
            values.push(node.value.as_ref());
        }
        Expr::SetComp(node) => values.push(node.elt.as_ref()),
        Expr::ListComp(node) => values.push(node.elt.as_ref()),
        _ => return None,
    }
    Some((first, rest, targets.0, values))
}

#[derive(Default)]
struct Targets(HashSet<String>);

impl<'a> Visitor<'a> for Targets {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(name) = expr {
            if name.ctx == ExprContext::Store {
                self.0.insert(name.id.to_string());
            }
        }
        visitor::walk_expr(self, expr);
    }
}
