// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The receiver sites of a body (AD-524, #1571): the place of each name that is the root of a
//! chain that the scan reads (the receiver of a method call, the initializer of a `let`, the value
//! of a `for`, a `match` or a `let` condition), without nested items and macros. A closure, a loop
//! or a pattern variable has a proof only at these places, and nested closures are left out. A
//! `let` sees into nested closures (`into_closures`): their parameters count as names bound again.

use std::collections::{BTreeMap, BTreeSet};

use syn::visit::{self, Visit};
use syn::{Expr, Item};

use crate::tokens::plain;

/// The longest receiver that the sites follow to its root.
const MAX_DEPTH: usize = 10;

#[derive(Default)]
pub(super) struct ClosureSites {
    pub(super) found: BTreeMap<String, BTreeSet<(usize, usize)>>,
    /// The names that a pattern of the body binds.
    pub(super) bound: BTreeSet<String>,
    /// The walk goes into nested closures.
    pub(super) into_closures: bool,
}

impl ClosureSites {
    /// Note the root name of a chain.
    pub(super) fn note(&mut self, expr: &Expr) {
        let mut receiver = expr;
        for _ in 0..MAX_DEPTH {
            receiver = match receiver {
                Expr::Field(found) if found.attrs.is_empty() => &found.base,
                Expr::MethodCall(found) if found.attrs.is_empty() => &found.receiver,
                Expr::Try(found) if found.attrs.is_empty() => &found.expr,
                Expr::Paren(found) if found.attrs.is_empty() => &found.expr,
                Expr::Reference(found) if found.attrs.is_empty() => &found.expr,
                _ => break,
            };
        }
        if let Expr::Path(path) = receiver {
            let name = path
                .path
                .get_ident()
                .filter(|_| path.qself.is_none() && path.attrs.is_empty());
            if let Some(name) = name {
                let at = name.span().start();
                self.found
                    .entry(plain(name))
                    .or_default()
                    .insert((at.line, at.column));
            }
        }
    }
}

impl<'ast> Visit<'ast> for ClosureSites {
    fn visit_item(&mut self, _: &'ast Item) {}
    fn visit_expr_closure(&mut self, node: &'ast syn::ExprClosure) {
        if self.into_closures {
            visit::visit_expr_closure(self, node);
        }
    }
    fn visit_pat_ident(&mut self, node: &'ast syn::PatIdent) {
        self.bound.insert(plain(&node.ident));
        visit::visit_pat_ident(self, node);
    }
    fn visit_expr_method_call(&mut self, node: &'ast syn::ExprMethodCall) {
        self.note(&node.receiver);
        visit::visit_expr_method_call(self, node);
    }
    fn visit_local(&mut self, node: &'ast syn::Local) {
        if let Some(init) = &node.init {
            self.note(&init.expr);
        }
        visit::visit_local(self, node);
    }
    fn visit_expr_for_loop(&mut self, node: &'ast syn::ExprForLoop) {
        self.note(&node.expr);
        visit::visit_expr_for_loop(self, node);
    }
    fn visit_expr_match(&mut self, node: &'ast syn::ExprMatch) {
        self.note(&node.expr);
        visit::visit_expr_match(self, node);
    }
    fn visit_expr_let(&mut self, node: &'ast syn::ExprLet) {
        self.note(&node.expr);
        visit::visit_expr_let(self, node);
    }
}
