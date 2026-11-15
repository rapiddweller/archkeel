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
//!
//! The same visitor reads the names that an import brings from another module of the scan. The
//! class of a `from m import C` that escapes in the importing module keeps no member in `m`. A
//! write whose base, or a `setattr`, `delattr` or `__setattr__` call whose argument, reaches an
//! imported name opens the module of that import, and so does a use of an imported module path
//! (`q.C`) that is no call, base, attribute load or annotation.

use std::collections::{HashMap, HashSet};

use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Expr, ExprAttribute, ExprCall, ExprContext, Parameter, Stmt, StmtClassDef, StmtFunctionDef,
};

use crate::module::Module;
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
pub(in crate::survey) struct Escapes {
    /// A write that the scan cannot tie to an instance: no class of the module keeps a member.
    pub open: bool,
    /// The classes of the module body that a use of their name can write through.
    pub escaped: HashSet<String>,
}

/// What a name that an import binds is: the module of the scan that it comes from and, for a
/// `from m import C`, the name `C` (a module path has none).
struct Origin {
    module: String,
    symbol: Option<String>,
}

/// The escapes of each module of the scan, in the order of `modules`: its own, and the ones that
/// the other modules cause through their imports.
pub(in crate::survey) fn all(
    modules: &[Module],
    binders: &[Binders],
    imports: &[Record<ImportFact>],
) -> Vec<Escapes> {
    let scan: HashSet<&str> = modules.iter().map(|module| module.name.as_str()).collect();
    let mut foreign: HashMap<&str, HashMap<String, Origin>> = HashMap::new();
    for record in imports {
        let data = record.data.data();
        let (Some(binding), target) = (&data.binding, data.target_module.as_str()) else {
            continue;
        };
        let child = data
            .symbol
            .as_ref()
            .map(|symbol| format!("{target}.{symbol}"));
        let origin = match (&data.symbol, child) {
            (Some(_), Some(child)) if scan.contains(child.as_str()) => Origin {
                module: child,
                symbol: None,
            },
            (symbol, _) => Origin {
                module: target.to_owned(),
                symbol: symbol.clone(),
            },
        };
        if scan.contains(origin.module.as_str()) {
            foreign
                .entry(data.source_module.as_str())
                .or_default()
                .insert(binding.clone(), origin);
        }
    }
    let mut opened = false;
    let mut named: HashSet<String> = HashSet::new();
    let mut found: Vec<Escapes> = Vec::new();
    let empty = HashMap::new();
    for (module, binders) in modules.iter().zip(binders) {
        let imported = foreign.get(module.name.as_str()).unwrap_or(&empty);
        let (own, cross) = scan_module(&module.tree.body, binders, imported);
        found.push(own);
        opened |= cross.opened;
        named.extend(cross.escaped);
    }
    // A write or an escape through an import reaches a class by a name that the scan cannot tie to
    // one module (a re-export), so it holds for each module: the stricter form.
    for escapes in &mut found {
        escapes.open |= opened;
        escapes.escaped.extend(named.iter().cloned());
    }
    found
}

/// The escapes of one module body, and what its imports let it do to other modules.
fn scan_module(
    body: &[Stmt],
    binders: &Binders,
    imported: &HashMap<String, Origin>,
) -> (Escapes, Cross) {
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
        imported,
        found: Escapes::default(),
        cross: Cross::default(),
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
    (walk.found, walk.cross)
}

/// What a module does to the classes of the others: a write through an import, and the names of
/// the imported classes that escape in it.
#[derive(Default)]
struct Cross {
    opened: bool,
    escaped: HashSet<String>,
}

struct Walk<'a> {
    /// The names of the classes of the module body.
    classes: HashSet<&'a str>,
    /// The classes of the module body that are no metaclass.
    plain: HashSet<String>,
    binders: &'a Binders,
    imported: &'a HashMap<String, Origin>,
    found: Escapes,
    cross: Cross,
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
                other if self.known(other) => {}
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
        let writer = match &*call.func {
            Expr::Name(callee) => matches!(callee.id.as_str(), "setattr" | "delattr" | "vars"),
            Expr::Attribute(callee) => {
                matches!(callee.attr.as_str(), "__setattr__" | "__delattr__")
            }
            _ => false,
        };
        if writer {
            self.found.open = true;
            self.reach(&call.func);
            for argument in &call.arguments.args {
                self.reach(argument);
            }
        }
        match &*call.func {
            callee if self.known(callee) => {}
            other => self.visit_expr(other),
        }
        for argument in &call.arguments.args {
            self.visit_expr(argument);
        }
        for keyword in &call.arguments.keywords {
            self.visit_expr(&keyword.value);
        }
    }

    /// True for the name of a class of the module, of an imported class, or a path below an
    /// imported module: a call, a base and an attribute load may hold it.
    fn known(&self, expr: &Expr) -> bool {
        match expr {
            Expr::Name(name) => {
                let name = name.id.as_str();
                let class = self
                    .imported
                    .get(name)
                    .is_some_and(|origin| origin.symbol.is_some());
                class || self.classes.contains(name)
            }
            Expr::Attribute(node) => self.module_path(&node.value),
            _ => false,
        }
    }

    /// A path of attributes whose root is a name that an import binds to a module.
    fn module_path(&self, expr: &Expr) -> bool {
        match expr {
            Expr::Name(name) => self
                .imported
                .get(name.id.as_str())
                .is_some_and(|origin| origin.symbol.is_none()),
            Expr::Attribute(node) => self.module_path(&node.value),
            _ => false,
        }
    }

    /// A use that reaches an imported name can write the class that it holds.
    fn reach(&mut self, expr: &Expr) {
        let mut names = Names::default();
        names.visit_expr(expr);
        let reached = names
            .found
            .iter()
            .any(|name| self.imported.contains_key(name.as_str()));
        self.cross.opened |= reached;
    }

    fn base_is_instance(&self, base: &Expr) -> bool {
        matches!(base, Expr::Name(name)
            if self.instance.as_deref() == Some(name.id.as_str()))
    }

    fn attribute(&mut self, node: &ExprAttribute) {
        let name = node.attr.as_str();
        if matches!(name, "__setattr__" | "__delattr__") {
            self.found.open = true;
            self.reach(&node.value);
        }
        let stored = matches!(node.ctx, ExprContext::Store | ExprContext::Del);
        if stored {
            self.reach(&node.value);
            self.found.open |= !self.base_is_instance(&node.value);
        }
        // A path below an imported module that is no call, base or attribute load reaches its
        // class: the module opens.
        self.cross.opened |= !self.annotation && self.module_path(&node.value);
        // An attribute load on a class is no escape of the class.
        match &*node.value {
            base if self.known(base) => {}
            other => self.visit_expr(other),
        }
    }
}

/// The names that an expression reads.
#[derive(Default)]
struct Names {
    found: Vec<String>,
}

impl<'a> Visitor<'a> for Names {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(name) = expr {
            self.found.push(name.id.to_string());
        }
        visitor::walk_expr(self, expr);
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
            Expr::Name(name) if !self.annotation && name.ctx == ExprContext::Load => {
                let name = name.id.as_str();
                if self.classes.contains(name) {
                    self.found.escaped.insert(name.to_owned());
                }
                match self.imported.get(name) {
                    Some(Origin {
                        symbol: Some(symbol),
                        ..
                    }) => {
                        self.cross.escaped.insert(symbol.clone());
                    }
                    Some(_) => self.cross.opened = true,
                    None => {}
                }
            }
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}
