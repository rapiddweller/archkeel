// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A reserved name that an exact `str` tests is data, not a dynamic import (AD-1340, #2196).
//!
//! `type(name) is str and name in {"__globals__", "__builtins__"}` lists names; it looks nothing up.
//! The proof is the type of the left operand, not the form of the text: an exact `str` has the
//! hooks of `str`, and a display of string literals builds without user code. Any other test of a
//! text can call `__eq__` of the other operand with the literal (a class of the scan, an inherited
//! hook, a metaclass, a rebound name), so it keeps the site.
//!
//! A string literal is inert when it stands in a comparison that:
//! - is the operand right after `type(name) is str` in an `and` chain (nothing stands between, so
//!   the name cannot be written in between), with one operator and the name on the left; and
//! - is `name in D`, `name not in D`, `name == "text"` or `name != "text"`, where `D` is a string
//!   literal, a set, tuple or list display of string literals only (or `frozenset`, `set`, `tuple`
//!   of one such display, with the builtin visible), or a name that the module binds once to such a
//!   display and uses only in tests of this form, and no other module of the scan imports it, reads
//!   it as an attribute, writes it as a string, or star-imports.
//!
//! Every other place of the literal keeps the gap.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{BoolOp, CmpOp, Expr, ExprContext, ModModule, Stmt};
use ruff_text_size::{Ranged, TextRange};

use crate::module::Module;
use crate::survey::binders::Binders;

/// The ranges of the inert string literals of each module.
pub(super) fn ranges(modules: &[Module], binders: &[Binders]) -> Vec<HashSet<TextRange>> {
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
                found: &mut found,
                uses: HashMap::new(),
            };
            tests.visit_body(&module.tree.body);
            let uses = tests.uses;
            for candidate in candidates {
                let (loads, tested) = uses.get(candidate.name.as_str()).copied().unwrap_or((0, 0));
                if tested > 0 && loads == tested && !outside.contains(candidate.name.as_str()) {
                    found.extend(candidate.elements.iter().copied());
                }
            }
            found
        })
        .collect()
}

/// A name that the module binds once to a display of string literals.
struct Candidate {
    name: String,
    elements: Vec<TextRange>,
}

/// The names that a statement of the module body itself binds to a display of string literals. A name in
/// a class body or a function is no candidate: Python reads some of them by itself (`__match_args__`,
/// `__slots__`); a dunder of the module is none either (`__all__` is read by `import *`).
fn candidates(tree: &ModModule, binders: &Binders) -> Vec<Candidate> {
    let walk = Assigns { binders };
    tree.body
        .iter()
        .filter_map(|stmt| walk.statement(stmt))
        .collect()
}

struct Assigns<'b> {
    binders: &'b Binders,
}

impl Assigns<'_> {
    fn statement(&self, stmt: &Stmt) -> Option<Candidate> {
        let (target, value) = match stmt {
            Stmt::Assign(node) => match node.targets.as_slice() {
                [target] => (target, Some(&*node.value)),
                _ => return None,
            },
            Stmt::AnnAssign(node) => (&*node.target, node.value.as_deref()),
            _ => return None,
        };
        self.candidate(target, value)
    }

    /// `name = display of strings`, when the module binds the name once.
    fn candidate(&self, target: &Expr, value: Option<&Expr>) -> Option<Candidate> {
        let (Expr::Name(name), Some(value)) = (target, value) else {
            return None;
        };
        let id = name.id.as_str();
        let dunder = id.starts_with("__") && id.ends_with("__");
        let elements = strings_of(value, &|builtin| self.binders.builtin_visible(builtin))?;
        (!dunder && self.binders.count(id) == Some(1)).then_some(())?;
        Some(Candidate {
            name: id.to_owned(),
            elements,
        })
    }
}

/// The ranges of the elements of a set, tuple or list display, or of `frozenset`, `set` or `tuple`
/// of one display, when each element is a string literal and the builtin is visible.
fn strings_of(value: &Expr, visible: &dyn Fn(&str) -> bool) -> Option<Vec<TextRange>> {
    let items: &[Expr] = match value {
        Expr::Set(node) => &node.elts,
        Expr::Tuple(node) => &node.elts,
        Expr::List(node) => &node.elts,
        Expr::Call(call) => {
            let Expr::Name(func) = &*call.func else {
                return None;
            };
            let builtin = matches!(func.id.as_str(), "frozenset" | "set" | "tuple");
            let plain = call.arguments.keywords.is_empty() && call.arguments.args.len() == 1;
            if !(builtin && plain && visible(func.id.as_str())) {
                return None;
            }
            return strings_of(&call.arguments.args[0], visible);
        }
        _ => return None,
    };
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

/// The guarded tests of the module, and for each name: its loads and the loads that stand in a guarded test.
struct Tests<'f> {
    visible: &'f dyn Fn(&str) -> bool,
    found: &'f mut HashSet<TextRange>,
    uses: HashMap<String, (usize, usize)>,
}

impl Tests<'_> {
    /// `type(name) is str and name in D`: the comparison right after the proof.
    fn guard(&mut self, values: &[Expr]) {
        for pair in values.windows(2) {
            let Some(proven) = exact_str(&pair[0], self.visible) else {
                continue;
            };
            if let Expr::Compare(node) = &pair[1] {
                self.guarded(&node.ops, &node.operands, proven);
            }
        }
    }

    /// One comparison with one operator and the proven name on the left.
    fn guarded(&mut self, ops: &[CmpOp], operands: &[Expr], proven: &str) {
        let ([op], [Expr::Name(left), right]) = (ops, operands) else {
            return;
        };
        if left.id.as_str() != proven {
            return;
        }
        match (op, right) {
            (CmpOp::Eq | CmpOp::NotEq, Expr::StringLiteral(text)) => {
                self.found.insert(text.range());
            }
            (CmpOp::In | CmpOp::NotIn, Expr::StringLiteral(text)) => {
                self.found.insert(text.range());
            }
            (CmpOp::In | CmpOp::NotIn, Expr::Name(name)) if name.ctx == ExprContext::Load => {
                self.uses.entry(name.id.to_string()).or_default().1 += 1;
            }
            (CmpOp::In | CmpOp::NotIn, display) => {
                self.found
                    .extend(strings_of(display, self.visible).into_iter().flatten());
            }
            _ => {}
        }
    }
}

/// The name of `type(name) is str`, with `type` and `str` the builtins. `==` is no proof: a
/// metaclass can define it; `isinstance` is none either.
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

impl<'a> Visitor<'a> for Tests<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::BoolOp(node) if node.op == BoolOp::And => self.guard(&node.values),
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
