// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The bindings of the names of the function `__getattr__` (AD-560).

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{ExceptHandler, Expr, ExprContext, Parameter, Stmt};
use ruff_text_size::{Ranged, TextSize};

use crate::survey::binders::import_bindings;

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum Abs {
    Entry,
    Keys,
    Items,
    Pos(usize),
    Globals,
    Other,
}

/// The bindings of the names of the function.
pub(super) struct Binds<'a> {
    pub table: &'a str,
    pub map: HashMap<String, Vec<Abs>>,
    pub handled: HashSet<TextSize>,
    /// The names that an assignment reads as an entry of the table.
    pub entries: Vec<String>,
    /// A nested scope, a `global` or a `match`: the function is not read.
    pub bad: bool,
}

impl Binds<'_> {
    fn is_table(&self, expr: &Expr) -> bool {
        matches!(expr, Expr::Name(node) if node.id.as_str() == self.table)
    }

    fn bind(&mut self, target: &Expr, abs: Abs) {
        match (target, abs) {
            (Expr::Name(node), Abs::Entry | Abs::Keys | Abs::Pos(_) | Abs::Globals) => {
                self.map.entry(node.id.to_string()).or_default().push(abs);
                self.handled.insert(node.start());
            }
            (Expr::Tuple(node), Abs::Entry) => {
                let plain = node.elts.iter().enumerate();
                for (index, element) in plain.filter(|(_, item)| !matches!(item, Expr::Starred(_)))
                {
                    self.bind(element, Abs::Pos(index));
                }
            }
            (Expr::Tuple(node), Abs::Items) if node.elts.len() == 2 => {
                self.bind(&node.elts[0], Abs::Keys);
                self.bind(&node.elts[1], Abs::Entry);
            }
            _ => {}
        }
    }

    fn other(&mut self, name: &str) {
        self.map
            .entry(name.to_owned())
            .or_default()
            .push(Abs::Other);
    }

    /// What the table gives for a value.
    fn value(&self, value: &Expr) -> Abs {
        match value {
            Expr::Call(call) => match &*call.func {
                Expr::Attribute(node)
                    if self.is_table(&node.value)
                        && node.attr.as_str() == "get"
                        && call.arguments.args.len() == 1
                        && call.arguments.keywords.is_empty() =>
                {
                    Abs::Entry
                }
                Expr::Name(node)
                    if node.id.as_str() == "globals"
                        && call.arguments.args.is_empty()
                        && call.arguments.keywords.is_empty() =>
                {
                    Abs::Globals
                }
                _ => Abs::Other,
            },
            Expr::Subscript(node)
                if self.is_table(&node.value) && node.ctx == ExprContext::Load =>
            {
                Abs::Entry
            }
            _ => Abs::Other,
        }
    }

    /// What iterating a value gives.
    fn iterated(&self, value: &Expr) -> Abs {
        let Expr::Call(call) = value else {
            return Abs::Other;
        };
        let Expr::Attribute(node) = &*call.func else {
            return Abs::Other;
        };
        if !self.is_table(&node.value) || !call.arguments.args.is_empty() {
            return Abs::Other;
        }
        match node.attr.as_str() {
            "items" => Abs::Items,
            "keys" => Abs::Keys,
            "values" => Abs::Entry,
            _ => Abs::Other,
        }
    }
}

impl<'a> Visitor<'a> for Binds<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(_)
            | Stmt::ClassDef(_)
            | Stmt::Global(_)
            | Stmt::Nonlocal(_)
            | Stmt::Match(_) => self.bad = true,
            Stmt::Assign(node) => {
                let unpack = node
                    .targets
                    .iter()
                    .all(|target| matches!(target, Expr::Tuple(_)));
                let abs = match &*node.value {
                    // An unpacking of a name that holds an entry of the table.
                    Expr::Name(name) if unpack => {
                        self.entries.push(name.id.to_string());
                        Abs::Entry
                    }
                    value => self.value(value),
                };
                node.targets
                    .iter()
                    .for_each(|target| self.bind(target, abs));
            }
            Stmt::AnnAssign(node) => {
                if let Some(value) = &node.value {
                    let abs = self.value(value);
                    self.bind(&node.target, abs);
                }
            }
            Stmt::For(node) => {
                let abs = self.iterated(&node.iter);
                self.bind(&node.target, abs);
            }
            Stmt::Import(_) | Stmt::ImportFrom(_) => {
                import_bindings(stmt)
                    .iter()
                    .for_each(|name| self.other(name));
            }
            Stmt::Try(node) => {
                for handler in &node.handlers {
                    let ExceptHandler::ExceptHandler(item) = handler;
                    item.name.iter().for_each(|name| self.other(name.as_str()));
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            if node.ctx != ExprContext::Load && !self.handled.contains(&node.start()) {
                self.other(node.id.as_str());
            }
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        self.other(parameter.name.as_str());
    }
}
