// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The writes to a class that its body does not show, and the classes that escape (AD-518,
//! rules 7 and 8): one fail-closed visitor of a module, in the shape of `uses.rs`.
//!
//! A member of a class is what its body binds only while nothing else writes the class. The
//! visitor opens the module (`open`: no class of it has a member) for an attribute store, `del`
//! or `+=` whose base is not a proven instance, for `setattr`, `delattr`, `vars` and any use of an
//! attribute named `__setattr__` or `__delattr__`. A base is a proven instance only as the first
//! parameter of an undecorated `def` directly in the body of a class whose bases are builtin or
//! of the module (so it is no metaclass), never rebound, and not of `__init_subclass__`,
//! `__class_getitem__` or `__new__`.
//!
//! A class of the module body escapes (`escaped`: it keeps no member) in each use of its name but
//! four: a call of it, a base of a class, an attribute load on it, and an annotation. A name that
//! is passed, stored, returned or decorated may be written by code that the scan does not link.

use std::collections::HashSet;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Expr, ExprAttribute, ExprCall, ExprContext, Parameter, Stmt, StmtClassDef, StmtFunctionDef,
};

use crate::survey::binders::Binders;
use crate::survey::bound::Bound;

/// The methods whose first parameter is not an instance of the class.
const NOT_INSTANCE: [&str; 3] = ["__init_subclass__", "__class_getitem__", "__new__"];

/// The builtin bases that make a class no metaclass (as the kind reader accepts them).
const PLAIN_BASES: [&str; 12] = [
    "object",
    "Exception",
    "BaseException",
    "ValueError",
    "TypeError",
    "RuntimeError",
    "KeyError",
    "dict",
    "list",
    "tuple",
    "str",
    "int",
];

/// What the visitor finds in a module.
#[derive(Default)]
pub(super) struct Escapes {
    /// A write that the scan cannot tie to an instance: no class of the module keeps a member.
    pub open: bool,
    /// The classes of the module body that a use of their name can write through.
    pub escaped: HashSet<String>,
}

/// The escapes of the module body `body`.
pub(super) fn of(body: &[Stmt], binders: &Binders) -> Escapes {
    let classes: HashSet<&str> = body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(node) => Some(node.name.as_str()),
            _ => None,
        })
        .collect();
    let mut walk = Walk {
        classes,
        plain: HashSet::new(),
        binders,
        found: Escapes::default(),
        instance: None,
        annotation: false,
    };
    for statement in body {
        if let Stmt::ClassDef(node) = statement {
            if walk.is_plain(node) {
                walk.plain.insert(node.name.to_string());
            }
        }
    }
    walk.visit_body(body);
    walk.found
}

struct Walk<'a> {
    /// The names of the classes of the module body.
    classes: HashSet<&'a str>,
    /// The classes of the module body that are no metaclass.
    plain: HashSet<String>,
    binders: &'a Binders,
    found: Escapes,
    /// The first parameter of the method that the walk is in: a proven instance.
    instance: Option<String>,
    /// The walk is in an annotation, where a class name is no escape.
    annotation: bool,
}

impl Walk<'_> {
    /// A class with no keyword whose bases are builtin classes or classes of the module that are
    /// themselves plain: a method of it gets an instance, never a class.
    fn is_plain(&self, node: &StmtClassDef) -> bool {
        let Some(arguments) = node.arguments.as_deref() else {
            return true;
        };
        arguments.keywords.is_empty()
            && arguments.args.iter().all(|base| match base {
                Expr::Name(name) => {
                    let name = name.id.as_str();
                    self.plain.contains(name)
                        || (PLAIN_BASES.contains(&name) && self.binders.builtin_visible(name))
                }
                _ => false,
            })
    }

    /// The name of the instance that `node` gets, when the method is proven.
    fn receiver(node: &StmtFunctionDef) -> Option<String> {
        let first = node
            .parameters
            .posonlyargs
            .iter()
            .chain(&node.parameters.args)
            .next()?;
        let name = first.parameter.name.as_str();
        let proven = node.decorator_list.is_empty()
            && !NOT_INSTANCE.contains(&node.name.as_str())
            && !Bound::of(&node.body).names().contains(name);
        proven.then(|| name.to_owned())
    }

    fn annotated(&mut self, expr: &Expr) {
        let before = std::mem::replace(&mut self.annotation, true);
        self.visit_expr(expr);
        self.annotation = before;
    }

    /// A definition inside the one that the walk is in has no proven instance.
    fn detached(&mut self, walk: impl FnOnce(&mut Self)) {
        let before = self.instance.take();
        walk(self);
        self.instance = before;
    }

    fn function(&mut self, node: &StmtFunctionDef, instance: Option<String>) {
        for decorator in &node.decorator_list {
            self.visit_decorator(decorator);
        }
        self.visit_parameters(&node.parameters);
        if let Some(returns) = &node.returns {
            self.annotated(returns);
        }
        let before = std::mem::replace(&mut self.instance, instance);
        self.visit_body(&node.body);
        self.instance = before;
    }

    fn class(&mut self, node: &StmtClassDef) {
        for decorator in &node.decorator_list {
            self.visit_decorator(decorator);
        }
        let arguments = node.arguments.as_deref();
        for base in arguments.map_or(&[][..], |arguments| &arguments.args) {
            match base {
                Expr::Name(name) if self.classes.contains(name.id.as_str()) => {}
                other => self.visit_expr(other),
            }
        }
        for keyword in arguments.map_or(&[][..], |arguments| &arguments.keywords) {
            self.visit_expr(&keyword.value);
        }
        let plain = self.is_plain(node);
        for statement in &node.body {
            match statement {
                Stmt::FunctionDef(method) if plain => {
                    let instance = Self::receiver(method);
                    self.function(method, instance);
                }
                other => self.visit_stmt(other),
            }
        }
    }

    fn call(&mut self, call: &ExprCall) {
        match &*call.func {
            // A call of a class of the module is no escape of the class.
            Expr::Name(callee) if self.classes.contains(callee.id.as_str()) => {}
            Expr::Name(callee) => {
                let opens = matches!(callee.id.as_str(), "setattr" | "delattr" | "vars");
                self.found.open |= opens;
                self.visit_expr(&call.func);
            }
            other => self.visit_expr(other),
        }
        for argument in &call.arguments.args {
            self.visit_expr(argument);
        }
        for keyword in &call.arguments.keywords {
            self.visit_expr(&keyword.value);
        }
    }

    fn base_is_instance(&self, base: &Expr) -> bool {
        matches!(base, Expr::Name(name)
            if self.instance.as_deref() == Some(name.id.as_str()))
    }

    fn attribute(&mut self, node: &ExprAttribute) {
        let name = node.attr.as_str();
        if matches!(name, "__setattr__" | "__delattr__") {
            self.found.open = true;
        }
        let stored = matches!(node.ctx, ExprContext::Store | ExprContext::Del);
        if stored && !self.base_is_instance(&node.value) {
            self.found.open = true;
        }
        // An attribute load on a class of the module is no escape of the class.
        match &*node.value {
            Expr::Name(base) if self.classes.contains(base.id.as_str()) => {}
            other => self.visit_expr(other),
        }
    }
}

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(node) => self.function(node, None),
            Stmt::ClassDef(node) => self.detached(|walk| walk.class(node)),
            Stmt::AnnAssign(node) => {
                self.visit_expr(&node.target);
                self.annotated(&node.annotation);
                node.value.iter().for_each(|value| self.visit_expr(value));
            }
            _ => visitor::walk_stmt(self, stmt),
        }
    }

    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        if let Some(annotation) = &parameter.annotation {
            self.annotated(annotation);
        }
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Lambda(_) => {
                self.detached(|walk| visitor::walk_expr(walk, expr));
                return;
            }
            Expr::Attribute(node) => {
                self.attribute(node);
                return;
            }
            Expr::Call(call) => {
                self.call(call);
                return;
            }
            Expr::Name(name)
                if !self.annotation
                    && name.ctx == ExprContext::Load
                    && self.classes.contains(name.id.as_str()) =>
            {
                self.found.escaped.insert(name.id.to_string());
            }
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}
