// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `__getattr__` of a lazy import module (AD-560): which import calls have arguments that
//! only the table gives, and which `globals()` writes only name a key of the table.
//!
//! An atom is a name whose every binding in the function unpacks a value that the function reads
//! from the table, or the requested name after a guard that returns when the table has no entry
//! for it. The function has no nested scope and no `global` or `nonlocal` statement.

use std::cell::RefCell;
use std::collections::{BTreeSet, HashMap};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    CmpOp, ConversionFlag, Expr, ExprCall, ExprContext, FStringPartRef, InterpolatedStringElement,
    Operator, Stmt, StmtFunctionDef,
};
use ruff_text_size::{Ranged, TextRange};

use super::lazy_binds::{Abs, Binds};
use super::lazy_shape::plain_parameter;
use super::lazy_shape::DUNDERS;
use super::lazy_table::Table;
use super::lazy_writes::Writes;

/// The most strings that one argument or one product may have.
pub(super) const LIMIT: usize = 4096;

/// The names, besides the module dunders (`DUNDERS`), that a written key must not equal: the rule
/// depends on them. A dunder is written by a `globals()` store as well, so both lists name it.
const DEPENDENT_BESIDES_DUNDERS: [&str; 4] = ["import_module", "importlib", "globals", "getattr"];

/// How the module proves the import function: a `from importlib import import_module` that is
/// its only binder, or plain `import importlib` statements that are the only binders.
#[derive(Clone, Copy)]
pub(super) struct Callee {
    pub from_import: bool,
    pub plain: bool,
}

/// One import call with the strings that its arguments can have.
pub(super) struct Call {
    pub range: TextRange,
    pub callee: TextRange,
    pub names: Vec<String>,
    pub packages: Option<Vec<String>>,
    pub by_name: bool,
}

#[derive(Default)]
pub(super) struct Flow {
    pub calls: Vec<Call>,
    pub exempt: Vec<TextRange>,
}

pub(super) fn analyze(function: &StmtFunctionDef, table: &Table, callee: Callee) -> Flow {
    let Some(param) = plain_parameter(function).map(|one| one.parameter.name.as_str()) else {
        return Flow::default();
    };
    let mut binds = Binds::new(&table.name);
    binds.visit_body(&function.body);
    // A name that an unpacking reads must hold an entry at each of its bindings.
    let entries_from = binds.entries.clone();
    let entries = binds.entries.iter().all(|name| {
        let all = binds.map.get(name);
        all.is_some_and(|all| all.iter().all(|abs| *abs == Abs::Entry))
    });
    if binds.bad || !entries {
        return Flow::default();
    }
    let scope = Scope {
        table,
        param,
        map: binds.map,
        guard: None,
        slots: false,
        callee,
        limits: RefCell::new(Vec::new()),
    };
    let found = scope.guard_index(&function.body);
    let held = found.as_ref().and_then(|item| item.1.clone());
    let slots = held.is_some_and(|name| entries_from.iter().all(|source| *source == name));
    let guard = found.map(|item| item.0);
    let scope = Scope {
        guard,
        slots,
        ..scope
    };
    let mut flow = Flow::default();
    for (index, stmt) in function.body.iter().enumerate() {
        let mut calls = Calls {
            scope: &scope,
            guarded: scope.guard.is_some_and(|at| index > at),
            found: Vec::new(),
        };
        calls.visit_stmt(stmt);
        flow.calls.extend(calls.found);
    }
    if !table.keys.iter().any(|key| collides(key, &table.name)) {
        flow.exempt = Writes::run(&function.body, scope.guard, &scope.map, &|name, guarded| {
            scope.atom(name, guarded).is_some()
        });
    }
    flow
}

fn collides(key: &str, table: &str) -> bool {
    key == table || DEPENDENT_BESIDES_DUNDERS.contains(&key) || DUNDERS.contains(&key)
}

pub(super) struct Scope<'a> {
    pub table: &'a Table,
    pub param: &'a str,
    pub map: HashMap<String, Vec<Abs>>,
    /// The index of the statement after which the requested name is a key of the table.
    pub guard: Option<usize>,
    /// Each unpacked entry is the entry of the requested name: its slots and the name go together.
    slots: bool,
    callee: Callee,
    /// The literal tests of the enclosing `if` statements: a name, a literal, equal or not.
    limits: RefCell<Vec<(String, String, bool)>>,
}

impl Scope<'_> {
    fn is_table(&self, expr: &Expr) -> bool {
        matches!(expr, Expr::Name(node) if node.id.as_str() == self.table.name)
    }

    /// The index of the first top-level `if` that returns or raises when the table has no entry
    /// for the requested name.
    fn guard_index(&self, body: &[Stmt]) -> Option<(usize, Option<String>)> {
        body.iter().enumerate().find_map(|(index, stmt)| {
            let Stmt::If(node) = stmt else { return None };
            let leaves = matches!(node.body.last(), Some(Stmt::Return(_) | Stmt::Raise(_)));
            let single = node.elif_else_clauses.is_empty();
            let compare = node.test.as_compare_expr()?;
            let [op] = &*compare.ops else {
                return None;
            };
            let [right] = compare.comparators() else {
                return None;
            };
            let Expr::Name(left) = compare.operands.first()? else {
                return None;
            };
            let proven = match op {
                CmpOp::NotIn => left.id.as_str() == self.param && self.is_table(right),
                CmpOp::Is if matches!(right, Expr::NoneLiteral(_)) => {
                    self.entry_of_param(&body[..index], left.id.as_str())
                }
                _ => false,
            };
            let held = matches!(op, CmpOp::Is).then(|| left.id.to_string());
            (leaves && single && proven).then_some((index, held))
        })
    }

    /// `name = table.get(param)` before the guard, and no other binder of `name`.
    fn entry_of_param(&self, before: &[Stmt], name: &str) -> bool {
        let once = matches!(self.map.get(name).map(Vec::as_slice), Some([Abs::Entry]));
        once && before.iter().any(|stmt| {
            let Stmt::Assign(node) = stmt else {
                return false;
            };
            let [Expr::Name(target)] = node.targets.as_slice() else {
                return false;
            };
            let Expr::Call(call) = &*node.value else {
                return false;
            };
            target.id.as_str() == name
                && self.table_method(call, "get")
                && matches!(call.arguments.args.as_ref(),
                    [Expr::Name(arg)] if arg.id.as_str() == self.param)
        })
    }

    fn table_method(&self, call: &ExprCall, method: &str) -> bool {
        matches!(&*call.func, Expr::Attribute(node)
            if self.is_table(&node.value) && node.attr.as_str() == method
                && call.arguments.keywords.is_empty())
    }

    /// The strings that a name can have.
    /// The entries of the table that the enclosing literal tests allow for the entry of the
    /// requested name: a test on a slot name keeps the entries with (or without) the literal.
    fn allowed(&self) -> Vec<&(String, Vec<String>)> {
        let limits = self.limits.borrow();
        let slot = |name: &str| match self.map.get(name).map(Vec::as_slice) {
            Some([Abs::Slot(index)]) if self.slots => Some(*index),
            _ => None,
        };
        let tests: Vec<(usize, &str, bool)> = limits
            .iter()
            .filter_map(|(name, text, equal)| Some((slot(name)?, text.as_str(), *equal)))
            .collect();
        let fits = |items: &Vec<String>| {
            tests.iter().all(|(index, text, equal)| {
                items
                    .get(*index)
                    .is_some_and(|item| (item == text) == *equal)
            })
        };
        self.table
            .entries
            .iter()
            .filter(|entry| fits(&entry.1))
            .collect()
    }

    pub(super) fn atom(&self, name: &str, guarded: bool) -> Option<BTreeSet<String>> {
        let allowed = self.allowed();
        if name == self.param {
            let keys = allowed.iter().map(|entry| entry.0.clone()).collect();
            return (guarded && !self.map.contains_key(name)).then_some(keys);
        }
        let mut out = BTreeSet::new();
        for abs in self.map.get(name)? {
            match abs {
                Abs::Keys => out.extend(self.table.keys.iter().cloned()),
                Abs::Pos(index) => out.extend(
                    self.table
                        .positions
                        .get(*index)
                        .into_iter()
                        .flatten()
                        .cloned(),
                ),
                Abs::Slot(index) => out.extend(
                    allowed
                        .iter()
                        .filter_map(|entry| entry.1.get(*index))
                        .cloned(),
                ),
                _ => return None,
            }
        }
        // A test `name == 'x'` or `name != 'x'` of an enclosing `if` narrows the set. The branch
        // must not bind the name again, so the test still holds at the use (`Calls`).
        for (_, text, equal) in self.limits.borrow().iter().filter(|item| item.0 == name) {
            if *equal {
                out.retain(|item| item == text);
            } else {
                out.remove(text);
            }
        }
        Some(out)
    }

    /// The strings of an argument built from literals, f-strings, `+` and atoms.
    fn strings(&self, expr: &Expr, guarded: bool) -> Option<BTreeSet<String>> {
        match expr {
            Expr::StringLiteral(text) => Some(BTreeSet::from([text.value.to_str().to_owned()])),
            Expr::Name(node) if node.ctx == ExprContext::Load => {
                self.atom(node.id.as_str(), guarded)
            }
            Expr::BinOp(node) if node.op == Operator::Add => {
                let left = self.strings(&node.left, guarded)?;
                join(&left, &self.strings(&node.right, guarded)?)
            }
            Expr::FString(node) => {
                let mut out = BTreeSet::from([String::new()]);
                for part in node.value.iter() {
                    out = join(&out, &self.part(part, guarded)?)?;
                }
                Some(out)
            }
            _ => None,
        }
    }

    fn part(&self, part: FStringPartRef, guarded: bool) -> Option<BTreeSet<String>> {
        let FStringPartRef::FString(fstring) = part else {
            let FStringPartRef::Literal(text) = part else {
                return None;
            };
            return Some(BTreeSet::from([text.value.to_string()]));
        };
        let mut out = BTreeSet::from([String::new()]);
        for element in fstring.elements.iter() {
            out = join(&out, &self.element(element, guarded)?)?;
        }
        Some(out)
    }

    fn element(
        &self,
        element: &InterpolatedStringElement,
        guarded: bool,
    ) -> Option<BTreeSet<String>> {
        match element {
            InterpolatedStringElement::Literal(text) => {
                Some(BTreeSet::from([text.value.to_string()]))
            }
            InterpolatedStringElement::Interpolation(field) => {
                let plain = field.debug_text.is_none()
                    && field.conversion == ConversionFlag::None
                    && field.format_spec.is_none();
                plain
                    .then(|| self.strings(&field.expression, guarded))
                    .flatten()
            }
        }
    }
}

fn join(left: &BTreeSet<String>, right: &BTreeSet<String>) -> Option<BTreeSet<String>> {
    if left.len().saturating_mul(right.len()) > LIMIT {
        return None;
    }
    let mut out = BTreeSet::new();
    for first in left {
        for second in right {
            out.insert(format!("{first}{second}"));
        }
    }
    Some(out)
}

/// The import calls of one top-level statement that the module proves and that the table bounds.
struct Calls<'a> {
    scope: &'a Scope<'a>,
    guarded: bool,
    found: Vec<Call>,
}

impl Calls<'_> {
    fn proven(&self, func: &Expr) -> Option<bool> {
        match func {
            Expr::Name(node) if node.id.as_str() == "import_module" => {
                self.scope.callee.from_import.then_some(true)
            }
            Expr::Attribute(node) if node.attr.as_str() == "import_module" => {
                let base =
                    matches!(&*node.value, Expr::Name(base) if base.id.as_str() == "importlib");
                (base && self.scope.callee.plain).then_some(false)
            }
            _ => None,
        }
    }

    fn call(&self, call: &ExprCall) -> Option<Call> {
        let by_name = self.proven(&call.func)?;
        let arguments = &call.arguments;
        let (name, package) = match (arguments.args.as_ref(), arguments.keywords.as_ref()) {
            ([name], []) => (name, None),
            ([name, package], []) => (name, Some(package)),
            ([name], [keyword])
                if keyword
                    .arg
                    .as_ref()
                    .is_some_and(|arg| arg.as_str() == "package") =>
            {
                (name, Some(&keyword.value))
            }
            _ => return None,
        };
        // The requested name as the whole module name is no module that the table gives.
        if matches!(name, Expr::Name(node) if node.id.as_str() == self.scope.param) {
            return None;
        }
        let names = self.scope.strings(name, self.guarded)?;
        let packages = match package {
            Some(expr) => Some(self.scope.strings(expr, self.guarded)?),
            None => None,
        };
        if names
            .len()
            .saturating_mul(packages.as_ref().map_or(1, BTreeSet::len))
            > LIMIT
        {
            return None;
        }
        Some(Call {
            range: call.range(),
            callee: call.func.range(),
            names: names.into_iter().collect(),
            packages: packages.map(|set| set.into_iter().collect()),
            by_name,
        })
    }
}

/// The test `name == 'x'` (or `!=`) as a name, a literal and whether they are equal.
fn literal_test(test: &Expr) -> Option<(String, String, bool)> {
    let compare = test.as_compare_expr()?;
    let ([Expr::Name(name), Expr::StringLiteral(text)], [op]) =
        (compare.operands.as_ref(), compare.ops.as_ref())
    else {
        return None;
    };
    let equal = match op {
        CmpOp::Eq => true,
        CmpOp::NotEq => false,
        _ => return None,
    };
    Some((name.id.to_string(), text.value.to_str().to_owned(), equal))
}

/// True when a statement list binds the name.
fn binds_name(body: &[Stmt], name: &str) -> bool {
    let mut binds = Binds::new(name);
    binds.visit_body(body);
    binds.map.contains_key(name)
}

impl<'a> Calls<'_> {
    /// An `if` with a literal test: the body and a plain `else` run under the test and its
    /// negation, when the name is not bound again inside.
    fn branch(&mut self, node: &'a ruff_python_ast::StmtIf) {
        let test = literal_test(&node.test);
        let plain = matches!(
            node.elif_else_clauses.as_slice(),
            [] | [ruff_python_ast::ElifElseClause { test: None, .. }]
        );
        self.visit_expr(&node.test);
        let limit = test.filter(|(name, _, _)| plain && !binds_name(&node.body, name));
        self.limited(limit.clone(), &node.body);
        for clause in &node.elif_else_clauses {
            clause.test.iter().for_each(|test| self.visit_expr(test));
            let other = limit
                .clone()
                .map(|(name, text, equal)| (name, text, !equal));
            let other = other.filter(|(name, _, _)| !binds_name(&clause.body, name));
            self.limited(other, &clause.body);
        }
    }

    fn limited(&mut self, limit: Option<(String, String, bool)>, body: &'a [Stmt]) {
        let pushed = limit.is_some();
        self.scope.limits.borrow_mut().extend(limit);
        self.visit_body(body);
        if pushed {
            self.scope.limits.borrow_mut().pop();
        }
    }
}

impl<'a> Visitor<'a> for Calls<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::If(node) => self.branch(node),
            _ => visitor::walk_stmt(self, stmt),
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Call(call) = expr {
            self.found.extend(self.call(call));
        }
        visitor::walk_expr(self, expr);
    }
}
