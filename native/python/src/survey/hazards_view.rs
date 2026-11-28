// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The receiver proofs of a read of a re-exported module name (AD-1540, #2142). The read is a
//! site unless its receiver is provably no module; see `hazards_class.rs` for the proven classes.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::name::Name;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext, Stmt, StmtAssign, StmtFunctionDef};

use super::class::Classes;

/// What the class and function that are being read prove about a receiver (AD-1540).
#[derive(Clone, Default)]
pub(super) struct View {
    /// The first parameter of the method, when its class is proven and the method keeps it.
    pub(super) receiver: Option<String>,
    /// The locals of the outermost function that hold one plain value.
    pub(super) plain: HashSet<String>,
    /// The class body: whether the class is proven.
    pub(super) class: Option<bool>,
}

/// True when a body binds a name again: an assignment, a loop or `with` target, a parameter of a
/// nested function or lambda, an import, a definition, an `except` name, a pattern or `global`.
pub(super) struct Rebinds<'a> {
    pub(super) name: &'a str,
    pub(super) found: bool,
}

impl<'a> Visitor<'a> for Rebinds<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let hit = match stmt {
            Stmt::FunctionDef(node) => node.name.as_str() == self.name,
            Stmt::ClassDef(node) => node.name.as_str() == self.name,
            Stmt::Import(node) => node.names.iter().any(|alias| {
                let bound = alias.asname.as_ref().unwrap_or(&alias.name);
                bound.as_str().split('.').next() == Some(self.name)
            }),
            Stmt::ImportFrom(node) => node
                .names
                .iter()
                .any(|alias| alias.asname.as_ref().unwrap_or(&alias.name).as_str() == self.name),
            Stmt::Global(node) => node.names.iter().any(|n| n.as_str() == self.name),
            Stmt::Nonlocal(node) => node.names.iter().any(|n| n.as_str() == self.name),
            _ => false,
        };
        self.found |= hit;
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(node) = expr {
            self.found |= node.ctx != ExprContext::Load && node.id.as_str() == self.name;
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_parameter(&mut self, parameter: &'a ruff_python_ast::Parameter) {
        self.found |= parameter.name.as_str() == self.name;
        visitor::walk_parameter(self, parameter);
    }

    fn visit_except_handler(&mut self, handler: &'a ruff_python_ast::ExceptHandler) {
        let ruff_python_ast::ExceptHandler::ExceptHandler(node) = handler;
        self.found |= node.name.as_ref().is_some_and(|n| n.as_str() == self.name);
        visitor::walk_except_handler(self, handler);
    }

    fn visit_pattern(&mut self, pattern: &'a ruff_python_ast::Pattern) {
        use ruff_python_ast::Pattern;
        let bound = match pattern {
            Pattern::MatchAs(node) => node.name.as_ref(),
            Pattern::MatchStar(node) => node.name.as_ref(),
            Pattern::MatchMapping(node) => node.rest.as_ref(),
            _ => None,
        };
        self.found |= bound.is_some_and(|n| n.as_str() == self.name);
        visitor::walk_pattern(self, pattern);
    }
}

/// The assignments of a function body, without the bodies of nested functions and classes.
pub(super) struct Assigns<'a>(pub(super) Vec<&'a StmtAssign>);

impl<'a> Visitor<'a> for Assigns<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(_) | Stmt::ClassDef(_) => {}
            Stmt::Assign(node) => self.0.push(node),
            _ => visitor::walk_stmt(self, stmt),
        }
    }
}

/// What the module and the scan prove about names: the proven classes, the import bindings, the
/// names that the module binds once and the names that `global` or `nonlocal` takes.
pub(super) struct Facts<'n> {
    pub(super) classes: &'n Classes,
    pub(super) module: &'n str,
    pub(super) imports: HashMap<String, Vec<String>>,
    pub(super) single: &'n HashSet<String>,
    pub(super) taken: HashSet<String>,
}

impl View {
    /// The receivers that a function or class statement proves for its body.
    pub(super) fn enter(&mut self, facts: &Facts, stmt: &Stmt, depth: usize) {
        match stmt {
            Stmt::FunctionDef(def) if depth == 0 => {
                self.plain = facts.plain_of(def);
                self.receiver = if self.class == Some(true) {
                    facts.receiver_of(def)
                } else {
                    None
                };
                self.class = None;
            }
            Stmt::FunctionDef(_) => self.class = None,
            Stmt::ClassDef(def) => {
                let qualified = format!("{}.{}", facts.module, def.name.as_str());
                *self = View {
                    class: Some(facts.classes.contains(&qualified)),
                    ..View::default()
                };
            }
            _ => {}
        }
    }

    /// The receivers after a statement: an outermost statement or a class gives back its own.
    pub(super) fn leave(&mut self, stmt: &Stmt, depth: usize, saved: View) {
        let own = depth == 0 || matches!(stmt, Stmt::ClassDef(_));
        let class = saved.class;
        if own {
            *self = saved;
        }
        self.class = class;
    }

    /// True when the receiver of an attribute read is provably no module: `self` of a method of
    /// a proven class that the method does not rebind, a local that holds one plain value, or a
    /// plain value itself. A parameter, an attribute and a call result stay unknown (AD-1540).
    pub(super) fn other(&self, facts: &Facts, receiver: &Expr) -> bool {
        match receiver {
            Expr::Name(node) => {
                let id = Name::as_str(&node.id);
                !facts.imports.contains_key(id)
                    && (self.receiver.as_deref() == Some(id) || self.plain.contains(id))
            }
            other => facts.plain_value(other),
        }
    }
}

impl Facts<'_> {
    /// A value that is no module: a literal, a display, a comprehension, or an instance of a
    /// proven class (AD-1540).
    pub(super) fn plain_value(&self, expr: &Expr) -> bool {
        match expr {
            Expr::StringLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::NoneLiteral(_)
            | Expr::EllipsisLiteral(_)
            | Expr::FString(_)
            | Expr::List(_)
            | Expr::Tuple(_)
            | Expr::Set(_)
            | Expr::Dict(_)
            | Expr::ListComp(_)
            | Expr::SetComp(_)
            | Expr::DictComp(_)
            | Expr::Generator(_) => true,
            Expr::Call(call) => self.constructs(&call.func),
            _ => false,
        }
    }

    /// A call of a name that is bound once, to a proven class of the scan.
    fn constructs(&self, callee: &Expr) -> bool {
        let Expr::Name(node) = callee else {
            return false;
        };
        let id = Name::as_str(&node.id);
        let once = !self.taken.contains(id) && self.single.contains(id);
        once && match self.imports.get(id).map(Vec::as_slice) {
            Some([origin]) => self.classes.contains(origin),
            Some(_) => false,
            None => self.classes.contains(&format!("{}.{id}", self.module)),
        }
    }

    /// The first parameter of a method of a proven class, when nothing in the method rebinds it.
    pub(super) fn receiver_of(&self, def: &StmtFunctionDef) -> Option<String> {
        let params = &def.parameters;
        let first = params.posonlyargs.iter().chain(&params.args).next()?;
        let plain = def.decorator_list.iter().all(|decorator| {
            matches!(&decorator.expression, Expr::Name(n)
                if ["property", "classmethod", "abstractmethod", "cached_property"]
                    .contains(&Name::as_str(&n.id)))
        });
        let name = first.parameter.name.as_str();
        let mut walk = Rebinds { name, found: false };
        walk.visit_body(&def.body);
        (plain && !walk.found && !self.taken.contains(name)).then(|| name.to_owned())
    }

    /// The locals of an outermost function that hold one plain value (AD-1540).
    pub(super) fn plain_of(&self, def: &StmtFunctionDef) -> HashSet<String> {
        let mut assigns = Assigns(Vec::new());
        assigns.visit_body(&def.body);
        let mut plain = HashSet::new();
        for node in assigns.0 {
            let [Expr::Name(target)] = node.targets.as_slice() else {
                continue;
            };
            let id = Name::as_str(&target.id);
            let once = !self.taken.contains(id) && self.single.contains(id);
            if once && self.plain_value(&node.value) {
                plain.insert(id.to_owned());
            }
        }
        plain
    }
}
