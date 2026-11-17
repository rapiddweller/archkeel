// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that a pattern of a body binds (#1571, AD-804): the parameter of a closure that is the
//! one argument of a fixed std adapter, the pattern of `for`, `if let`, `while let` and of a match
//! arm. Each name of the pattern (`scan_chains::destructure`) has the chain of the matched value
//! and the steps to it. It holds only at the receiver sites of its body (the closure, the loop,
//! the branch, the arm body), and only when the body binds the name nowhere else and no
//! `use` or macro call of the `fn` names it.

use std::collections::BTreeSet;

use syn::visit::{self, Visit};
use syn::{Expr, Item, Pat};

use super::chains::{chain_of, destructure, Names};
use super::sites::ClosureSites;
use crate::definitions::{ReceiverChain, Root};
use crate::tokens::plain;

/// The std adapters whose closure parameter has the item of the iterator (AD-804).
const ADAPTERS: [&str; 13] = [
    "map",
    "filter",
    "filter_map",
    "find",
    "any",
    "all",
    "for_each",
    "flat_map",
    "take_while",
    "skip_while",
    "position",
    "max_by_key",
    "min_by_key",
];

/// The bindings of a `fn` that a body adds to.
pub(super) trait Binder: Names {
    /// Bind a name to its chain at the receiver sites of its body.
    fn bind_at(&mut self, name: String, origin: ReceiverChain, sites: BTreeSet<(usize, usize)>);
}

/// The walk over the body of a `fn`, without nested items.
pub(super) struct Bodies<'a> {
    pub(super) binder: &'a mut dyn Binder,
    /// The names that a `use` or a macro call of the `fn` may bind.
    pub(super) tainted: &'a BTreeSet<String>,
}

impl Bodies<'_> {
    /// Bind the names of `pattern` to the parts of the value `of`, at their sites in `body`.
    fn pattern(
        &mut self,
        pattern: &Pat,
        of: Option<ReceiverChain>,
        body: &dyn Fn(&mut ClosureSites),
    ) {
        let Some(of) = of else {
            return;
        };
        let mut sites = ClosureSites::default();
        body(&mut sites);
        for (name, steps) in destructure(pattern) {
            if self.tainted.contains(&name) || sites.bound.contains(&name) {
                continue;
            }
            let Some(places) = sites.found.remove(&name) else {
                continue;
            };
            let mut origin = of.clone();
            origin.name.clone_from(&name);
            origin.steps.extend(steps);
            origin.macros = self.binder.macros();
            self.binder.bind_at(name, origin, places);
        }
    }

    /// The names of the pattern of an `if let` or `while let` condition, in its block.
    fn condition(&mut self, (cond, attrs): (&Expr, &[syn::Attribute]), block: &syn::Block) {
        if let (Expr::Let(found), true) = (cond, attrs.is_empty()) {
            let body = |sites: &mut ClosureSites| sites.visit_block(block);
            let of = self.value(&found.expr).filter(|_| found.attrs.is_empty());
            self.pattern(&found.pat, of, &body);
        }
    }

    /// The chain of a matched value.
    fn value(&self, expr: &Expr) -> Option<ReceiverChain> {
        let names: &dyn Names = &*self.binder;
        chain_of(expr, names)
    }

    /// The element of the iterator of `of` for an adapter or `for`.
    fn element(&self, of: &Expr, adapter: &str) -> Option<ReceiverChain> {
        Some(ReceiverChain {
            name: String::new(),
            root: Root::Element(Box::new(self.value(of)?), adapter.to_owned()),
            steps: Vec::new(),
            macros: self.binder.macros(),
        })
    }
}

impl<'ast> Visit<'ast> for Bodies<'_> {
    fn visit_item(&mut self, _: &'ast Item) {}

    fn visit_expr_method_call(&mut self, node: &'ast syn::ExprMethodCall) {
        let adapter = plain(&node.method);
        if let (true, Some(Expr::Closure(closure))) = (
            ADAPTERS.contains(&adapter.as_str()) && node.args.len() == 1,
            node.args.first(),
        ) {
            if let [input] = closure.inputs.iter().collect::<Vec<_>>().as_slice() {
                let body = |sites: &mut ClosureSites| sites.visit_expr(&closure.body);
                let of = self.element(&node.receiver, &adapter);
                self.pattern(input, of, &body);
            }
        }
        visit::visit_expr_method_call(self, node);
    }

    fn visit_expr_for_loop(&mut self, node: &'ast syn::ExprForLoop) {
        if node.attrs.is_empty() {
            let body = |sites: &mut ClosureSites| sites.visit_block(&node.body);
            let of = self.element(&node.expr, "for");
            self.pattern(&node.pat, of, &body);
        }
        visit::visit_expr_for_loop(self, node);
    }

    fn visit_expr_if(&mut self, node: &'ast syn::ExprIf) {
        self.condition((&node.cond, &node.attrs), &node.then_branch);
        visit::visit_expr_if(self, node);
    }

    fn visit_expr_while(&mut self, node: &'ast syn::ExprWhile) {
        self.condition((&node.cond, &node.attrs), &node.body);
        visit::visit_expr_while(self, node);
    }

    fn visit_expr_match(&mut self, node: &'ast syn::ExprMatch) {
        if node.attrs.is_empty() {
            let of = self.value(&node.expr);
            for arm in node.arms.iter().filter(|arm| arm.attrs.is_empty()) {
                let body = |sites: &mut ClosureSites| sites.visit_expr(&arm.body);
                self.pattern(&arm.pat, of.clone(), &body);
            }
        }
        visit::visit_expr_match(self, node);
    }
}
