// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The attribute names that code stores on any value, for the lazy annotations of Python 3.14
//! (#1523, AD-802).
//!
//! On Python 3.14 a method annotation is evaluated when it is read, in the namespace of its class
//! (PEP 649). The namespace can get a name after the class statement: `Box.object = Hidden`,
//! `setattr(Box, "object", v)`, `type.__setattr__(Box, "object", v)`. A store does not say whether
//! its value is a class, so each attribute store counts. A store with a computed name, and a use
//! of `setattr` or `__setattr__` as a value, can write any name.

use std::collections::HashSet;

use ruff_python_ast::name::Name;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprCall, ExprContext, Identifier, ModModule, Stmt};

/// The functions that write an attribute by a name in an argument.
const WRITERS: [&str; 4] = ["setattr", "delattr", "__setattr__", "__delattr__"];

/// The attribute names that the files store, or every name.
#[derive(Default)]
pub(crate) struct ClassWrites {
    names: HashSet<String>,
    any: bool,
    /// A store through a namespace (`vars(x)[k]`, `x.__dict__[k]`, `sys.modules[k]`,
    /// `globals()[k]`) or code run from a text: it can change any name of any module (AD-782).
    /// The lazy annotations of #1523 do not read it: a class namespace is no such mapping.
    namespace: bool,
    /// A source file at an import root can shadow the standard library (AD-880).
    shadowed: HashSet<String>,
}

/// The methods of a mapping that change it.
const MUTATORS: [&str; 7] = [
    "update",
    "setdefault",
    "pop",
    "popitem",
    "clear",
    "__setitem__",
    "__delitem__",
];

/// The functions that run code from a text.
const RUNNERS: [&str; 3] = ["exec", "eval", "compile"];

impl ClassWrites {
    /// Add the stores of one file.
    pub(super) fn add(&mut self, tree: &ModModule) {
        Walk(self).visit_body(&tree.body);
        // `from sys import modules` gives `sys.modules` a name that the walk does not follow.
        self.namespace |= imports_from(tree, "sys", "modules");
    }

    /// True when a class namespace can get `name` after the class statement.
    pub(crate) fn can_write(&self, name: &str) -> bool {
        self.any || self.names.contains(name)
    }

    /// Why code of the repository may change the attribute `name` of a module, if it may
    /// (AD-782): a store of that name, a store with a computed name, or a namespace store.
    pub(crate) fn change_of(&self, name: &str) -> Option<&'static str> {
        if self.namespace {
            return Some(
                "a store through vars, __dict__, sys.modules or globals, or code run from a text",
            );
        }
        if self.any {
            return Some("an attribute store with a computed name");
        }
        HashSet::contains(&self.names, name).then_some("an attribute store of this name")
    }
}

impl ClassWrites {
    /// Record a module name that can be imported directly from one of the source roots.
    pub(super) fn add_path(&mut self, roots: &HashSet<String>, rel: &str) {
        let source =
            str::strip_suffix(rel, "/__init__.py").or_else(|| str::strip_suffix(rel, ".py"));
        let native = || {
            let suffix = str::rsplit_once(rel, '.')?.1;
            matches!(suffix, "so" | "pyd").then_some(rel)
        };
        let Some(module) = source.or_else(native) else {
            return;
        };
        let (directory, name) = str::rsplit_once(module, '/').unwrap_or(("", module));
        if !str::is_empty(directory) && !HashSet::contains(roots, directory) {
            return;
        }
        let name = str::split_once(name, '.').map_or(name, |(module, _)| module);
        self.shadowed.insert(name.to_owned());
    }

    /// True when a local import root can resolve this name ahead of the standard library.
    pub(super) fn shadows(&self, module: &str) -> bool {
        HashSet::contains(&self.shadowed, module)
    }

    /// True when the repository has no evidence of a change to the standard loader.
    pub(super) fn importlib_unchanged(&self) -> bool {
        !self.shadows("importlib")
            && !["importlib", "import_module", "__class__", "__import__"]
                .into_iter()
                .any(|name| may_write(self, name))
    }

    /// Nothing in the repository can replace the `Any` of the standard module `typing` (AD-880): no
    /// file shadows `typing`, and no store (a name, a computed name, `sys.modules`, a namespace)
    /// can change `Any`.
    pub(super) fn typing_unchanged(&self) -> bool {
        self.typing_holds("Any")
    }

    /// True when no store can change the standard class forms that the Any inventory admits.
    pub(super) fn annotation_classes_unchanged(&self) -> bool {
        [
            "TYPE_CHECKING",
            "__bases__",
            "__build_class__",
            "__call__",
            "__class__",
            "__class_getitem__",
            "__closure__",
            "__code__",
            "__defaults__",
            "__globals__",
            "__init_subclass__",
            "__kwdefaults__",
            "__mro_entries__",
            "__new__",
            "__prepare__",
            "_TypedDictMeta",
            "_add_slots",
            "_process_class",
            "EnumType",
        ]
        .into_iter()
        .all(|name| self.change_of(name).is_none())
    }

    /// True when no observed file shadows typing or can write this attribute of it.
    pub(super) fn typing_holds(&self, name: &str) -> bool {
        !self.shadows("typing") && Option::is_none(&ClassWrites::change_of(self, name))
    }
}

/// True when repository code may change a name, including a store through a namespace.
pub(crate) fn may_write(writes: &ClassWrites, name: &str) -> bool {
    writes.any || writes.namespace || HashSet::contains(&writes.names, name)
}

/// True when the module has `from __future__ import annotations`: its annotations are strings.
pub(crate) fn future_annotations(tree: &ModModule) -> bool {
    imports_from(tree, "__future__", "annotations")
}

/// True when the module body has `from <module> import <name>`, with or without an alias.
fn imports_from(tree: &ModModule, module: &str, name: &str) -> bool {
    tree.body.iter().any(|stmt| {
        matches!(stmt, Stmt::ImportFrom(node) if node.level == 0
            && node.module.as_ref().is_some_and(|found| Identifier::as_str(found) == module)
            && node.names.iter().any(|found| Identifier::as_str(&found.name) == name))
    })
}

struct Walk<'w>(&'w mut ClassWrites);

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            // A read of a namespace: an item load, or a method that does not change it.
            Expr::Subscript(node) if node.ctx == ExprContext::Load && namespace(&node.value) => {
                self.visit_expr(&node.slice);
                return;
            }
            Expr::Subscript(node) if node.ctx != ExprContext::Load && namespace(&node.value) => {
                self.0.namespace = true;
                self.visit_expr(&node.slice);
                return;
            }
            Expr::Call(node) if read_of_namespace(&node.func) => {
                for argument in &node.arguments.args {
                    self.visit_expr(argument);
                }
                for keyword in &node.arguments.keywords {
                    self.visit_expr(&keyword.value);
                }
                return;
            }
            // Any other use of a namespace can change it, and so can code run from a text.
            _ if namespace(expr) || runner(expr) => self.0.namespace = true,
            Expr::Attribute(node) if node.ctx != ExprContext::Load => {
                self.0.names.insert(node.attr.to_string());
            }
            Expr::Call(node) if writer(&node.func) => {
                self.call(node);
                // The callee is read here; its arguments can hold more stores.
                for argument in &node.arguments.args {
                    self.visit_expr(argument);
                }
                for keyword in &node.arguments.keywords {
                    self.visit_expr(&keyword.value);
                }
                return;
            }
            // A writer used as a value can be called with any name.
            _ if writer(expr) => self.0.any = true,
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

impl Walk<'_> {
    /// A call of a writer: the literal name in its first two arguments, or any name.
    fn call(&mut self, node: &ExprCall) {
        let literal = node
            .arguments
            .args
            .iter()
            .take(2)
            .find_map(|argument| match argument {
                Expr::StringLiteral(text) => Some(text.value.to_str().to_owned()),
                _ => None,
            });
        match literal {
            Some(name) => {
                self.0.names.insert(name);
            }
            None => self.0.any = true,
        }
    }
}

/// True for `setattr`, `delattr` or an attribute `__setattr__` or `__delattr__`.
fn writer(expr: &Expr) -> bool {
    match expr {
        Expr::Name(name) => WRITERS[..2].contains(&Name::as_str(&name.id)),
        Expr::Attribute(node) => WRITERS[2..].contains(&Identifier::as_str(&node.attr)),
        _ => false,
    }
}

/// `vars(x)`, `globals()`, `x.__dict__` or `sys.modules`: a mapping that holds the names of a
/// module or an object.
fn namespace(expr: &Expr) -> bool {
    match expr {
        Expr::Call(node) => match &*node.func {
            Expr::Name(name) => match Name::as_str(&name.id) {
                "vars" => !node.arguments.args.is_empty() || !node.arguments.keywords.is_empty(),
                "globals" => true,
                _ => false,
            },
            _ => false,
        },
        Expr::Attribute(node) => match Identifier::as_str(&node.attr) {
            "__dict__" | "__annotations__" | "__dataclass_fields__" => true,
            "modules" => {
                matches!(&*node.value, Expr::Name(name) if Name::as_str(&name.id) == "sys")
            }
            _ => namespace(&node.value),
        },
        Expr::Subscript(node) => namespace(&node.value),
        _ => false,
    }
}

/// A method of a namespace that reads it and does not change it.
fn read_of_namespace(func: &Expr) -> bool {
    match func {
        Expr::Attribute(node) => {
            namespace(&node.value) && !MUTATORS.contains(&Identifier::as_str(&node.attr))
        }
        _ => false,
    }
}

/// `exec`, `eval` or `compile`: code run from a text can store any name.
fn runner(expr: &Expr) -> bool {
    matches!(expr, Expr::Name(name) if RUNNERS.contains(&Name::as_str(&name.id)))
}
