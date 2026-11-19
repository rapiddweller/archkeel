// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that a pattern of a body binds (#1571, AD-804): the parameter of a closure that is the
//! one argument of a fixed std adapter, the pattern of `for`, `if let`, `while let` and of a match
//! arm, and of a `let` in a nested block or of a name that the `fn` binds more than once (a
//! top-level `let` of a name bound once is `read_locals`). Each name of the pattern (`scan_chains::destructure`) has the chain of the matched value
//! and the steps to it. It holds only at the receiver sites of its body (the closure, the loop,
//! the branch, the arm body), and only when the body binds the name nowhere else and no
//! `use` or macro call of the `fn` names it. A `let` holds in the statements after it, up to the next
//! `let` of the name in its block (whose initializer still sees it), also in nested closures.

use std::collections::{BTreeMap, BTreeSet};

use syn::visit::{self, Visit};
use syn::{Expr, Item, Pat, Stmt};

use super::chains::{chain_of, destructure, Names};
use super::params::Params;
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

/// The initializer (if any) of a statement that is a `let` of `name`, or `None` for another one.
fn shadow<'s>(statement: &'s Stmt, name: &str) -> Option<Option<&'s Expr>> {
    let Stmt::Local(next) = statement else {
        return None;
    };
    let binds = destructure(&next.pat)
        .iter()
        .any(|(other, _)| other == name);
    binds.then(|| next.init.as_ref().map(|init| &*init.expr))
}

/// The sites of a `let` of `name` in the statements after it: up to the next `let` of the name,
/// with the initializer of that one, and into nested closures.
fn let_sites(rest: &[Stmt], name: &str) -> ClosureSites {
    let mut sites = ClosureSites {
        into_closures: true,
        ..ClosureSites::default()
    };
    for statement in rest {
        let Some(init) = shadow(statement, name) else {
            sites.visit_stmt(statement);
            continue;
        };
        if let Some(init) = init {
            sites.note(init);
            sites.visit_expr(init);
        }
        break;
    }
    sites
}

/// The walk over the body of a `fn`, without nested items.
pub(super) struct Bodies<'a> {
    pub(super) binder: &'a mut Params,
    /// The names that a `use` or a macro call of the `fn` may bind.
    pub(super) tainted: &'a BTreeSet<String>,
    /// How many times the `fn` binds each name.
    pub(super) counts: &'a BTreeMap<String, usize>,
    /// The depth of the blocks of the walk: 0 outside the body of the `fn`.
    pub(super) depth: usize,
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
        for part in destructure(pattern) {
            self.bind(&of, part, &mut sites);
        }
    }

    /// Bind one name to its part of the value `of` at its sites, unless the body binds it again or a
    /// `use` or macro call of the `fn` names it.
    fn bind(
        &mut self,
        of: &ReceiverChain,
        (name, steps): (String, Vec<crate::definitions::Step>),
        sites: &mut ClosureSites,
    ) {
        if self.tainted.contains(&name) || sites.bound.contains(&name) {
            return;
        }
        let Some(places) = sites.found.remove(&name) else {
            return;
        };
        let mut origin = of.clone();
        origin.name.clone_from(&name);
        origin.steps.extend(steps);
        origin.macros = self.binder.macros();
        self.binder.bind_at(name, origin, places);
    }

    /// Bind the names of a `let` at their sites in the statements `rest` after it.
    fn local(&mut self, local: &syn::Local, rest: &[Stmt]) {
        let Some(init) = local.init.as_ref().filter(|_| local.attrs.is_empty()) else {
            return;
        };
        let (pattern, of) = match &local.pat {
            Pat::Type(typed) => {
                let Pat::Ident(ident) = &*typed.pat else {
                    return;
                };
                let of = self.binder.typed(&plain(&ident.ident), &typed.ty);
                (&*typed.pat, of.filter(|_| typed.attrs.is_empty()))
            }
            other => (other, self.value(&init.expr)),
        };
        let Some(of) = of else {
            return;
        };
        let top = self.depth == 1;
        for part in destructure(pattern) {
            if top && self.counts.get(&part.0) == Some(&1) {
                continue;
            }
            let mut sites = let_sites(rest, &part.0);
            self.bind(&of, part, &mut sites);
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
        chain_of(expr, self.binder)
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

    fn visit_block(&mut self, node: &'ast syn::Block) {
        self.depth += 1;
        for (at, statement) in node.stmts.iter().enumerate() {
            self.visit_stmt(statement);
            if let Stmt::Local(local) = statement {
                self.local(local, &node.stmts[at + 1..]);
            }
        }
        self.depth -= 1;
    }

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
