// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The table of a lazy import module (AD-560): a module-level name bound once to a dict literal
//! that has string keys and tuple values, and that the module only reads.
//!
//! A tuple item is a string literal or the package of the file (`__spec__.parent`,
//! `__package__`, and `__name__` of a package `__init__`) when the module never binds any of
//! these names. The table has one set of strings for each tuple position, over all entries.

use std::collections::{BTreeSet, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{CmpOp, Expr, ExprContext, Stmt};
use ruff_text_size::{Ranged, TextRange};

use crate::module::Module;

pub(super) struct Table {
    pub name: String,
    pub keys: BTreeSet<String>,
    /// The strings that all entries have at each tuple position.
    pub positions: Vec<BTreeSet<String>>,
    /// The ranges of the `__spec__.parent` reads of the table.
    pub exempt: Vec<TextRange>,
}

/// The package that `__spec__.parent` names in a module.
pub(super) fn parent(module: &Module) -> String {
    if module.is_init() {
        module.name.clone()
    } else {
        module
            .name
            .rsplit_once('.')
            .map_or("", |part| part.0)
            .to_owned()
    }
}

/// The one valid table of the module among the names `used`, or `None`.
pub(super) fn find(
    module: &Module,
    count: &dyn Fn(&str) -> Option<usize>,
    used: &HashSet<String>,
) -> Option<Table> {
    let mut found = module
        .tree
        .body
        .iter()
        .filter_map(|stmt| table(stmt, module, count, used))
        .filter(|(table, stmt)| count(&table.name) == Some(1) && read_only(module, table, stmt));
    let (first, _) = found.next()?;
    found.next().is_none().then_some(first)
}

fn table<'a>(
    stmt: &'a Stmt,
    module: &Module,
    count: &dyn Fn(&str) -> Option<usize>,
    used: &HashSet<String>,
) -> Option<(Table, &'a Stmt)> {
    let (target, value) = match stmt {
        Stmt::Assign(node) => match node.targets.as_slice() {
            [target] => (target, &*node.value),
            _ => return None,
        },
        Stmt::AnnAssign(node) => (&*node.target, &**node.value.as_ref()?),
        _ => return None,
    };
    let (Expr::Name(name), Expr::Dict(dict)) = (target, value) else {
        return None;
    };
    if !used.contains(name.id.as_str()) {
        return None;
    }
    let mut table = Table {
        name: name.id.to_string(),
        keys: BTreeSet::new(),
        positions: Vec::new(),
        exempt: Vec::new(),
    };
    for item in &dict.items {
        let Some(Expr::StringLiteral(key)) = &item.key else {
            return None;
        };
        table.keys.insert(key.value.to_str().to_owned());
        let Expr::Tuple(tuple) = &item.value else {
            return None;
        };
        for (index, element) in tuple.elts.iter().enumerate() {
            let text = atom(element, module, count, &mut table.exempt)?;
            if table.positions.len() <= index {
                table.positions.resize_with(index + 1, BTreeSet::new);
            }
            table.positions[index].insert(text);
        }
    }
    Some((table, stmt))
}

/// A tuple item: a literal, or the known package of the file.
fn atom(
    expr: &Expr,
    module: &Module,
    count: &dyn Fn(&str) -> Option<usize>,
    exempt: &mut Vec<TextRange>,
) -> Option<String> {
    let unbound = |name: &str| count(name) == Some(0);
    match expr {
        Expr::StringLiteral(text) => Some(text.value.to_str().to_owned()),
        Expr::Attribute(node)
            if node.attr.as_str() == "parent"
                && node.ctx == ExprContext::Load
                && matches!(&*node.value, Expr::Name(base) if base.id.as_str() == "__spec__")
                && unbound("__spec__") =>
        {
            exempt.push(expr.range());
            Some(parent(module))
        }
        Expr::Name(name) if name.id.as_str() == "__package__" && unbound("__package__") => {
            Some(parent(module))
        }
        Expr::Name(name)
            if name.id.as_str() == "__name__" && module.is_init() && unbound("__name__") =>
        {
            Some(module.name.clone())
        }
        _ => None,
    }
}

/// True when each other use of the table name is a read: `get`, `items`, `keys`, `values`,
/// a subscript load, or the right side of `in`.
fn read_only(module: &Module, table: &Table, defining: &Stmt) -> bool {
    let mut reads = Reads {
        name: &table.name,
        ok: true,
    };
    for stmt in &module.tree.body {
        if stmt.range() != defining.range() {
            reads.visit_stmt(stmt);
        }
    }
    reads.ok
}

struct Reads<'a> {
    name: &'a str,
    ok: bool,
}

impl Reads<'_> {
    fn is_table(&self, expr: &Expr) -> bool {
        matches!(expr, Expr::Name(node) if node.id.as_str() == self.name)
    }
}

impl<'a> Visitor<'a> for Reads<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(_) if self.is_table(expr) => self.ok = false,
            Expr::Call(call) => match &*call.func {
                Expr::Attribute(node)
                    if self.is_table(&node.value)
                        && matches!(node.attr.as_str(), "get" | "items" | "keys" | "values") =>
                {
                    call.arguments
                        .args
                        .iter()
                        .for_each(|arg| self.visit_expr(arg));
                    call.arguments
                        .keywords
                        .iter()
                        .for_each(|keyword| self.visit_expr(&keyword.value));
                }
                _ => visitor::walk_expr(self, expr),
            },
            Expr::Subscript(node)
                if self.is_table(&node.value) && node.ctx == ExprContext::Load =>
            {
                self.visit_expr(&node.slice);
            }
            Expr::Compare(node) => {
                node.operands
                    .first()
                    .into_iter()
                    .for_each(|left| self.visit_expr(left));
                let pairs = node.ops.iter().zip(node.comparators());
                let reads: Vec<&Expr> = pairs
                    .filter(|(op, item)| {
                        !(matches!(op, CmpOp::In | CmpOp::NotIn) && self.is_table(item))
                    })
                    .map(|(_, item)| item)
                    .collect();
                reads.into_iter().for_each(|item| self.visit_expr(item));
            }
            _ => visitor::walk_expr(self, expr),
        }
    }
}
