// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The receiver sites of a closure body or a loop body (AD-524, #1571): the place of each name
//! that is the root of the receiver of a method call, without nested items, macros or closures. A
//! closure parameter or a loop variable has a proof only at these places.

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
}

impl<'ast> Visit<'ast> for ClosureSites {
    fn visit_item(&mut self, _: &'ast Item) {}
    fn visit_expr_closure(&mut self, _: &'ast syn::ExprClosure) {}
    fn visit_pat_ident(&mut self, node: &'ast syn::PatIdent) {
        self.bound.insert(plain(&node.ident));
        visit::visit_pat_ident(self, node);
    }
    fn visit_expr_method_call(&mut self, node: &'ast syn::ExprMethodCall) {
        let mut receiver = &*node.receiver;
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
        visit::visit_expr_method_call(self, node);
    }
}
