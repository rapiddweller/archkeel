// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A narrow proof that a module has no written class declarations (AD-726), and the first call
//! that can create a class at run time (#1713).

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprCall, ExprContext, ModModule, Stmt};
use ruff_text_size::{Ranged, TextRange};

/// Plain imports and undecorated functions can form the module body. A class anywhere, a
/// namespace escape, or an eagerly evaluated function header leaves the inventory unread.
pub(super) fn empty(tree: &ModModule) -> bool {
    let future = tree.body.iter().any(|stmt| {
        matches!(stmt, Stmt::ImportFrom(node) if node.level == 0
            && node.module.as_ref().is_some_and(|name| name.as_str() == "__future__")
            && node.names.iter().any(|name| name.name.as_str() == "annotations"))
    });
    let plain = tree.body.iter().all(|stmt| match stmt {
        Stmt::Import(_) | Stmt::ImportFrom(_) => true,
        Stmt::Expr(node) => matches!(&*node.value, Expr::StringLiteral(_)),
        Stmt::FunctionDef(node) => {
            let params = &node.parameters;
            let mut items = params
                .posonlyargs
                .iter()
                .chain(&params.args)
                .chain(&params.kwonlyargs);
            let unsafe_header = items
                .any(|p| p.default.is_some() || (!future && p.parameter.annotation.is_some()))
                || (!future
                    && (node.returns.is_some()
                        || params
                            .vararg
                            .iter()
                            .chain(&params.kwarg)
                            .any(|p| p.annotation.is_some())));
            node.decorator_list.is_empty() && node.type_params.is_none() && !unsafe_header
        }
        _ => false,
    });
    let mut walk = Walk::default();
    walk.visit_body(&tree.body);
    plain && !walk.classes && !walk.unsafe_namespace && factory_site(tree).is_none()
}

/// A namespace operation in one module can change another module of the scan.
pub(in crate::survey) fn namespace_safe(tree: &ModModule) -> bool {
    let mut walk = Walk::default();
    walk.visit_body(&tree.body);
    !walk.unsafe_namespace
}

#[derive(Default)]
struct Walk {
    classes: bool,
    unsafe_namespace: bool,
}

impl<'a> Visitor<'a> for Walk {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::ClassDef(_) => self.classes = true,
            Stmt::Global(_) => self.unsafe_namespace = true,
            Stmt::ImportFrom(node)
                if node.names.iter().any(|name| name.name.as_str() == "*")
                    || node
                        .module
                        .as_ref()
                        .is_some_and(|name| name.as_str() == "builtins") =>
            {
                self.unsafe_namespace = true;
            }
            Stmt::Import(node)
                if node
                    .names
                    .iter()
                    .any(|name| name.name.as_str() == "builtins") =>
            {
                self.unsafe_namespace = true;
            }
            Stmt::FunctionDef(node) if node.name.as_str() == "__getattr__" => {
                self.unsafe_namespace = true;
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(node)
                if matches!(
                    node.id.as_str(),
                    "type"
                        | "exec"
                        | "eval"
                        | "globals"
                        | "locals"
                        | "vars"
                        | "setattr"
                        | "delattr"
                        | "__import__"
                        | "__builtins__"
                ) =>
            {
                self.unsafe_namespace = true;
            }
            Expr::Attribute(node)
                if node.ctx != ExprContext::Load || node.attr.as_str() == "__dict__" =>
            {
                self.unsafe_namespace = true;
            }
            Expr::Subscript(node) if node.ctx != ExprContext::Load => self.unsafe_namespace = true,
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

/// The qualified names whose call can create a class (#1713): the builder of the class statement,
/// the factories of the standard library and their metaclasses. `type` creates one with three
/// arguments.
const FACTORIES: [&str; 17] = [
    "builtins.__build_class__",
    "enum.Enum",
    "enum.IntEnum",
    "enum.Flag",
    "enum.IntFlag",
    "enum.StrEnum",
    "enum.ReprEnum",
    "enum.EnumMeta",
    "enum.EnumType",
    "collections.namedtuple",
    "typing.NamedTuple",
    "typing.TypedDict",
    "typing_extensions.NamedTuple",
    "typing_extensions.TypedDict",
    "dataclasses.make_dataclass",
    "types.new_class",
    "abc.ABCMeta",
];

/// The first call of the module that can create a class, with the callee that it names (#1713):
/// a call of a factory (by the import that binds its name), `type` with three arguments, a call
/// in the shape of a metaclass call (`M("Name", (...), {...})`), and a call whose result the
/// module uses as a class: it calls it, or passes it as the class of `isinstance` or `issubclass`.
/// Python runs such a call when the function that holds it runs, so the class that it creates
/// has no proven place.
pub(super) fn factory_site(tree: &ModModule) -> Option<(TextRange, String)> {
    let mut walk = Factories::default();
    walk.visit_body(&tree.body);
    walk.called = walk.made.clone();
    walk.found = None;
    walk.visit_body(&tree.body);
    walk.found
}

#[derive(Default)]
struct Factories {
    /// The origin of each name that an import of the module binds, in any scope.
    origins: HashMap<String, String>,
    /// The names that an assignment binds to the result of a call.
    made: HashSet<String>,
    /// In the second walk: the names whose call result the module may use as a class.
    called: HashSet<String>,
    found: Option<(TextRange, String)>,
}

impl Factories {
    /// The qualified name of a callee, from the import that binds its first name.
    fn origin(&self, expr: &Expr) -> Option<String> {
        match expr {
            Expr::Name(node) => {
                let name = node.id.as_str();
                (self.origins.get(name).cloned()).or_else(|| {
                    matches!(name, "type" | "__build_class__").then(|| format!("builtins.{name}"))
                })
            }
            Expr::Attribute(node) => Some(format!("{}.{}", self.origin(&node.value)?, node.attr)),
            _ => None,
        }
    }

    /// The callee that the call names when it can create a class.
    fn creates(&self, call: &ExprCall) -> Option<String> {
        let args = &call.arguments.args;
        let origin = self.origin(&call.func);
        if let Some(origin) = origin.as_deref() {
            if FACTORIES.contains(&origin) || (origin == "builtins.type" && args.get(2).is_some()) {
                return Some(origin.to_owned());
            }
        }
        let shape = matches!(
            (args.first(), args.get(1), args.get(2)),
            (
                Some(Expr::StringLiteral(_)),
                Some(Expr::Tuple(_)),
                Some(Expr::Dict(_))
            )
        );
        if shape {
            return Some(origin.unwrap_or_else(|| "a metaclass call".to_owned()));
        }
        let result_called = matches!(&*call.func, Expr::Call(_))
            || matches!(&*call.func, Expr::Name(name) if self.called.contains(name.id.as_str()));
        let class_test = matches!(&*call.func, Expr::Name(name)
            if matches!(name.id.as_str(), "isinstance" | "issubclass"))
            && matches!(args.get(1), Some(Expr::Call(_)));
        (result_called || class_test).then(|| "a call result used as a class".to_owned())
    }

    fn bind(&mut self, stmt: &Stmt) {
        match stmt {
            Stmt::Import(node) => {
                let bound = node.names.iter().map(|alias| {
                    let full = alias.name.as_str();
                    let top = full.split('.').next().unwrap_or(full);
                    match &alias.asname {
                        Some(name) => (name.to_string(), full.to_owned()),
                        None => (top.to_owned(), top.to_owned()),
                    }
                });
                self.origins.extend(bound);
            }
            Stmt::ImportFrom(node) if node.level == 0 => {
                let module = node.module.as_ref().map_or("", |name| name.as_str());
                for alias in &node.names {
                    let name = alias.asname.as_ref().unwrap_or(&alias.name);
                    self.origins
                        .insert(name.to_string(), format!("{module}.{}", alias.name));
                }
            }
            Stmt::Assign(node) if matches!(&*node.value, Expr::Call(_)) => {
                let names = node.targets.iter().filter_map(|target| match target {
                    Expr::Name(name) => Some(name.id.to_string()),
                    _ => None,
                });
                self.made.extend(names);
            }
            _ => {}
        }
    }
}

impl<'a> Visitor<'a> for Factories {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        self.bind(stmt);
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if self.found.is_some() {
            return;
        }
        if let Expr::Call(call) = expr {
            if let Some(callee) = self.creates(call) {
                self.found = Some((call.range(), callee));
                return;
            }
        }
        visitor::walk_expr(self, expr);
    }
}
