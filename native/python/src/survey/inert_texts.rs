// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A reserved name that is only tested is data, not a dynamic import (AD-1340, #2196).
//!
//! `name in {"__globals__", "__builtins__"}` lists names; it looks nothing up. One closed rule: a
//! string literal is inert when it is an element of a set, tuple or list display that is the right
//! side of `in` or `not in`, or the right side itself, or an operand of `==` or `!=`. A display
//! that is bound to a name counts too, when the module binds the name once, each other use of the
//! name is the right side of an `in` test, and no other module of the scan imports or reads that
//! name. A scan that defines `__eq__` or `__ne__` has no inert text in a comparison or in a list or
//! tuple test (the hook runs with the literal), and none in a set test when a class also defines
//! `__hash__`. Any other place of the literal keeps the gap: an argument of `getattr`, `__import__`, any
//! call, a store, a return, a dict key, a `match` case, an iteration of the bound display.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{BoolOp, CmpOp, Expr, ExprContext, ModModule, Stmt};
use ruff_text_size::{Ranged, TextRange};

use crate::module::Module;
use crate::survey::binders::Binders;

/// The ranges of the inert string literals of each module.
pub(super) fn ranges(modules: &[Module], binders: &[Binders]) -> Vec<HashSet<TextRange>> {
    let hooks = Hooks::of(modules);
    let bound: Vec<Vec<Candidate>> = modules
        .iter()
        .zip(binders)
        .map(|(module, binders)| candidates(&module.tree, binders))
        .collect();
    let wanted: HashSet<&str> = bound
        .iter()
        .flatten()
        .map(|candidate| candidate.name.as_str())
        .collect();
    let outside = if wanted.is_empty() {
        HashSet::new()
    } else {
        named_outside(modules, &wanted)
    };
    modules
        .iter()
        .zip(binders)
        .zip(bound.iter())
        .map(|((module, binders), candidates)| {
            let mut found = HashSet::new();
            let mut tests = Tests {
                visible: &|name| binders.builtin_visible(name),
                hooks,
                guarded: HashSet::new(),
                found: &mut found,
                uses: HashMap::new(),
            };
            tests.visit_body(&module.tree.body);
            let uses = tests.uses;
            for candidate in candidates.iter() {
                let (loads, in_tests) =
                    uses.get(candidate.name.as_str()).copied().unwrap_or((0, 0));
                let tested = in_tests > 0 && loads == in_tests;
                if tested
                    && hooks.allows(candidate.set)
                    && !outside.contains(candidate.name.as_str())
                {
                    found.extend(candidate.elements.iter().copied());
                }
            }
            found
        })
        .collect()
}

/// The equality hooks of the scan. A comparison calls `__eq__` of the other operand, which then holds
/// the literal; a set test calls it only when the hash of the operand collides, so it needs a class
/// that defines `__hash__` too.
#[derive(Clone, Copy, Default)]
struct Hooks {
    /// A statement defines or writes `__eq__` or `__ne__`.
    eq: bool,
    /// The scan defines or writes `__eq__` or `__ne__` and also `__hash__`: a subclass can inherit one and
    /// define the other, so the two need not stand in one class.
    pair: bool,
}

impl Hooks {
    fn of(modules: &[Module]) -> Hooks {
        let mut watch = Watch::default();
        modules
            .iter()
            .for_each(|module| watch.visit_body(&module.tree.body));
        Hooks {
            eq: watch.eq,
            pair: watch.eq && watch.hash,
        }
    }

    /// Whether a literal in a set (`set`) or in a sequence is data.
    fn allows(self, set: bool) -> bool {
        if set {
            !self.pair
        } else {
            !self.eq
        }
    }
}

#[derive(Default)]
struct Watch {
    eq: bool,
    hash: bool,
}

impl<'a> Visitor<'a> for Watch {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let defined = match stmt {
            Stmt::FunctionDef(node) => Some(node.name.as_str()),
            Stmt::Assign(node) => match node.targets.as_slice() {
                [Expr::Name(name)] => Some(name.id.as_str()),
                _ => None,
            },
            Stmt::AnnAssign(node) => match &*node.target {
                Expr::Name(name) => Some(name.id.as_str()),
                _ => None,
            },
            _ => None,
        };
        self.note(defined);
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        // A store `K.__eq__ = f`, a text `setattr(K, '__eq__', f)` or `type('K', (), {'__eq__': f})`.
        let written = match expr {
            Expr::Attribute(node) if node.ctx != ExprContext::Load => Some(node.attr.as_str()),
            Expr::StringLiteral(text) => Some(text.value.to_str()),
            _ => None,
        };
        self.note(written);
        visitor::walk_expr(self, expr);
    }
}

impl Watch {
    fn note(&mut self, name: Option<&str>) {
        self.eq |= matches!(name, Some("__eq__" | "__ne__"));
        self.hash |= name == Some("__hash__");
    }
}

/// A name that the module binds once to a display of strings.
struct Candidate {
    name: String,
    elements: Vec<TextRange>,
    /// The display is a set: a test hashes the other operand before it compares.
    set: bool,
}

fn candidates(tree: &ModModule, binders: &Binders) -> Vec<Candidate> {
    let mut walk = Assigns {
        found: Vec::new(),
        binders,
    };
    walk.visit_body(&tree.body);
    walk.found
}

struct Assigns<'b> {
    found: Vec<Candidate>,
    binders: &'b Binders,
}

impl Assigns<'_> {
    /// `name = display of strings`, when the module binds the name once.
    fn candidate(&self, target: &Expr, value: Option<&Expr>) -> Option<Candidate> {
        let (Expr::Name(name), Some(value)) = (target, value) else {
            return None;
        };
        let id = name.id.as_str();
        let (items, set) = display_of(value, &|builtin| self.binders.builtin_visible(builtin))?;
        (self.binders.count(id) == Some(1)).then_some(())?;
        let elements = strings(items)?;
        Some(Candidate {
            name: id.to_owned(),
            elements,
            set,
        })
    }
}

impl<'a> Visitor<'a> for Assigns<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let (target, value) = match stmt {
            Stmt::Assign(node) => match node.targets.as_slice() {
                [target] => (target, Some(&*node.value)),
                _ => return visitor::walk_stmt(self, stmt),
            },
            Stmt::AnnAssign(node) => (&*node.target, node.value.as_deref()),
            _ => return visitor::walk_stmt(self, stmt),
        };
        self.found.extend(self.candidate(target, value));
        visitor::walk_stmt(self, stmt);
    }
}

/// The elements of a set, tuple or list display, or of `frozenset(display)` with the builtin visible,
/// and whether the container is a set.
fn display_of<'e>(value: &'e Expr, visible: &dyn Fn(&str) -> bool) -> Option<(&'e [Expr], bool)> {
    match value {
        Expr::Set(node) => Some((&node.elts, true)),
        Expr::Tuple(node) => Some((&node.elts, false)),
        Expr::List(node) => Some((&node.elts, false)),
        Expr::Call(call) => {
            let Expr::Name(func) = &*call.func else {
                return None;
            };
            let set = matches!(func.id.as_str(), "frozenset" | "set");
            let builtin = set || func.id.as_str() == "tuple";
            let plain = call.arguments.keywords.is_empty() && call.arguments.args.len() == 1;
            if builtin && plain && visible(func.id.as_str()) {
                display_of(&call.arguments.args[0], visible).map(|(items, _)| (items, set))
            } else {
                None
            }
        }
        _ => None,
    }
}

/// The ranges of the elements when each one is a string literal.
fn strings(items: &[Expr]) -> Option<Vec<TextRange>> {
    items
        .iter()
        .map(|item| match item {
            Expr::StringLiteral(text) => Some(text.range()),
            _ => None,
        })
        .collect()
}

/// The names of `wanted` that another place of the scan imports, reads as an attribute, or writes
/// as a string (`__all__`, `getattr(module, "NAME")`).
fn named_outside<'m>(modules: &'m [Module], wanted: &HashSet<&'m str>) -> HashSet<&'m str> {
    let mut found = HashSet::new();
    for module in modules {
        let mut walk = Outside {
            wanted,
            found: &mut found,
        };
        walk.visit_body(&module.tree.body);
    }
    found
}

struct Outside<'w, 'f> {
    wanted: &'w HashSet<&'f str>,
    found: &'w mut HashSet<&'f str>,
}

impl<'a> Visitor<'a> for Outside<'_, '_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::ImportFrom(node) = stmt {
            // A star import takes each public name of its module.
            let star = node.names.iter().any(|alias| alias.name.as_str() == "*");
            let named = node
                .names
                .iter()
                .filter_map(|alias| self.wanted.get(alias.name.as_str()));
            self.found.extend(named);
            if star {
                self.found.extend(self.wanted.iter().copied());
            }
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        let text = match expr {
            Expr::Attribute(node) => Some(node.attr.as_str()),
            Expr::StringLiteral(node) => Some(node.value.to_str()),
            _ => None,
        };
        if let Some(name) = text.and_then(|text| self.wanted.get(text)) {
            self.found.insert(name);
        }
        visitor::walk_expr(self, expr);
    }
}

/// The tests of the module, and for each name: its loads and the loads that are an `in` test.
struct Tests<'f> {
    visible: &'f dyn Fn(&str) -> bool,
    hooks: Hooks,
    /// The comparisons whose left operand is a name that `type(name) is str` proves an exact `str`.
    guarded: HashSet<TextRange>,
    found: &'f mut HashSet<TextRange>,
    uses: HashMap<String, (usize, usize)>,
}

impl Tests<'_> {
    fn right_side_of_in(&mut self, side: &Expr, hooks: Hooks) {
        match side {
            Expr::StringLiteral(text) => {
                self.found.insert(text.range());
            }
            Expr::Name(name) if name.ctx == ExprContext::Load => {
                self.uses.entry(name.id.to_string()).or_default().1 += 1;
            }
            other => {
                let shown = display_of(other, self.visible);
                let items = shown.filter(|(_, set)| hooks.allows(*set));
                self.found
                    .extend(items.into_iter().flat_map(|(items, _)| strings_in(items)));
            }
        }
    }
}

/// The ranges of the string literals among the elements.
fn strings_in(items: &[Expr]) -> impl Iterator<Item = TextRange> + '_ {
    items.iter().filter_map(|item| match item {
        Expr::StringLiteral(text) => Some(text.range()),
        _ => None,
    })
}

impl Tests<'_> {
    /// `type(name) is str and name in {...}`: the comparison right after the proof has an exact `str` on the
    /// left. Nothing stands between them, so the name cannot be written in between.
    fn guard(&mut self, values: &[Expr]) {
        for pair in values.windows(2) {
            let proven: HashSet<&str> = exact_str(&pair[0], self.visible).into_iter().collect();
            self.guarded.extend(guarded_compare(&pair[1], &proven));
        }
    }

    /// One comparison `a op b op c`: the pairs of neighbours.
    fn compare(&mut self, ops: &[CmpOp], operands: &[Expr], guarded: bool) {
        // An exact `str` has the hooks of `str`: no code of the scan runs with the literal.
        let hooks = if guarded {
            Hooks::default()
        } else {
            self.hooks
        };
        for (at, op) in ops.iter().enumerate() {
            let (left, right) = (&operands[at], &operands[at + 1]);
            match op {
                CmpOp::In | CmpOp::NotIn => self.right_side_of_in(right, hooks),
                CmpOp::Eq | CmpOp::NotEq if hooks.allows(false) => {
                    self.found.extend(text_range(left).chain(text_range(right)))
                }
                _ => {}
            }
        }
    }
}

/// The range of a one-step comparison whose left operand is a proven name.
fn guarded_compare(value: &Expr, proven: &HashSet<&str>) -> Option<TextRange> {
    let Expr::Compare(node) = value else {
        return None;
    };
    let first = matches!(&node.operands[0], Expr::Name(n) if proven.contains(n.id.as_str()));
    (first && node.ops.len() == 1).then(|| node.range())
}

/// The name of `type(name) is str`, with `type` and `str` the builtins. `==` is no proof: a metaclass
/// can define it.
fn exact_str<'e>(value: &'e Expr, visible: &dyn Fn(&str) -> bool) -> Option<&'e str> {
    let Expr::Compare(node) = value else {
        return None;
    };
    let ([CmpOp::Is], [Expr::Call(call), Expr::Name(right)]) = (&*node.ops, &*node.operands) else {
        return None;
    };
    let Expr::Name(func) = &*call.func else {
        return None;
    };
    let [Expr::Name(arg)] = &*call.arguments.args else {
        return None;
    };
    let builtins = func.id.as_str() == "type" && right.id.as_str() == "str";
    let plain = call.arguments.keywords.is_empty() && visible("type") && visible("str");
    (builtins && plain).then_some(arg.id.as_str())
}

/// The range of a string literal operand.
fn text_range(side: &Expr) -> impl Iterator<Item = TextRange> {
    match side {
        Expr::StringLiteral(text) => Some(text.range()),
        _ => None,
    }
    .into_iter()
}

impl<'a> Visitor<'a> for Tests<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::BoolOp(node) if node.op == BoolOp::And => self.guard(&node.values),
            Expr::Compare(node) => {
                let guarded = self.guarded.contains(&node.range());
                self.compare(&node.ops, &node.operands, guarded);
            }
            Expr::Name(name) if name.ctx == ExprContext::Load => {
                self.uses.entry(name.id.to_string()).or_default().0 += 1;
            }
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

#[cfg(test)]
#[path = "inert_texts_tests.rs"]
mod tests;
