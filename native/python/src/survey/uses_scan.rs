// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The call of a name that makes an instance of a class of the scan (AD-566).
//!
//! An instance is no module object, so a use of it cannot change a module namespace. A call of a
//! name makes an instance of the class only when Python cannot run another constructor: the class
//! has no base and no keyword (its metaclass is `type`), its body binds no `__new__`, and each
//! decorator is `dataclasses.dataclass`. A store or a delete of `__new__` or `__class__`, a call of
//! `setattr` or `delattr`, or a use of `__setattr__` or `__delattr__` on anything but `object`
//! (`object.__setattr__` raises on a class) anywhere in the scan withholds the proof.

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, ExprContext};

use std::collections::{HashMap, HashSet};

use super::bound::{Bound, Kind};
use super::uses_typing_guard::{withheld, STDLIB_VALUES};
use crate::module::Module;

/// The module and the symbol that an import names.
pub(super) type Origin<'m> = (&'m str, Option<&'m str>);

/// The facts that the visitor reads about the scan.
pub(super) struct Scan<'m> {
    pub(super) modules: HashSet<&'m str>,
    pub(super) bounds: HashMap<&'m str, Bound>,
    pub(super) hazardous: HashSet<&'m str>,
    pub(super) typing_values: HashSet<(String, String)>,
    /// A statement of the scan can change the class of a class or its `__new__` (AD-566).
    pub(super) class_patch: bool,
    /// The imports of each module by bound name: (target module, symbol).
    pub(super) imports: HashMap<(&'m str, &'m str), Vec<Origin<'m>>>,
}

impl Scan<'_> {
    /// True when `name` is not a module, following plain re-exports.
    pub(super) fn callable(&self, module: &str, name: &str, depth: usize) -> bool {
        let Some(bound) = self.readable(module, name, depth) else {
            return false;
        };
        match bound.kind(name) {
            Some(Kind::Call) => {
                bound
                    .callee(name)
                    .is_some_and(|callee| self.constructs(module, callee, 0))
                    || self
                        .typing_values
                        .contains(&(module.to_owned(), name.to_owned()))
            }
            Some(Kind::Callable | Kind::Value) => true,
            // A name or a builtin call that reads only inert names (AD-530).
            Some(Kind::Derived) => bound.deps(name).is_some_and(|deps| {
                deps.builtins.iter().all(|builtin| bound.unbound(builtin))
                    && deps.names.iter().all(|read| {
                        // A name that the module does not bind is a builtin or an error.
                        bound.unbound(read) || self.callable(module, read, depth + 1)
                    })
            }),
            Some(Kind::BuiltinGeneric(builtin)) => bound.unbound(builtin),
            Some(Kind::Other)
                if self
                    .typing_values
                    .contains(&(module.to_owned(), name.to_owned())) =>
            {
                true
            }
            Some(Kind::Import) => match self.imports.get(&(module, name)).map(Vec::as_slice) {
                // An object of a module outside the scan; code outside the scan hands in no
                // module of the scan (AD-530).
                Some([(target, _)]) if !self.modules.contains(target) => true,
                Some([(target, Some(symbol))]) => self.callable(target, symbol, depth + 1),
                _ => false,
            },
            _ => false,
        }
    }

    /// The module and each module below it.
    pub(super) fn below(&self, module: &str) -> Vec<String> {
        let child = format!("{module}.");
        let names = self.modules.iter().copied();
        names
            .filter(|name| *name == module || name.starts_with(&child))
            .map(str::to_owned)
            .collect()
    }

    /// The bindings of `module` when the name `name` in it can be read as one plain binder.
    pub(super) fn readable(&self, module: &str, name: &str, depth: usize) -> Option<&Bound> {
        self.bounds.get(module).filter(|bound| {
            depth < 8
                && !bound.getattr
                && !bound.attribute_write
                && !self.hazardous.contains(module)
                && !self.modules.contains(format!("{module}.{name}").as_str())
        })
    }

    /// True when a call of `name` makes an instance of a class of the scan (AD-566): the name is
    /// a class without base, keyword or `__new__`, and each decorator is `dataclasses.dataclass`.
    pub(super) fn constructs(&self, module: &str, name: &str, depth: usize) -> bool {
        let Some(bound) = self
            .readable(module, name, depth)
            .filter(|_| !self.class_patch)
        else {
            return false;
        };
        match bound.kind(name) {
            Some(Kind::Callable) => bound.bare_class(name).is_some_and(|decorators| {
                decorators.iter().all(|decorator| {
                    decorator
                        .as_deref()
                        .is_some_and(|d| self.dataclass(module, d))
                })
            }),
            Some(Kind::Import) => match self.imports.get(&(module, name)).map(Vec::as_slice) {
                Some([(target, Some(symbol))]) if self.stdlib_value(target, symbol) => true,
                Some([(target, Some(symbol))]) => self.constructs(target, symbol, depth + 1),
                _ => false,
            },
            _ => false,
        }
    }

    /// True when `target.symbol` is a standard library name whose call gives a value (AD-568).
    fn stdlib_value(&self, target: &str, symbol: &str) -> bool {
        STDLIB_VALUES.contains(&(target, symbol)) && !self.modules.contains(target)
    }

    /// True when `name` in `module` is the one plain import of `dataclasses.dataclass`, and no
    /// module of the scan shadows `dataclasses`.
    fn dataclass(&self, module: &str, name: &str) -> bool {
        !self.modules.contains("dataclasses")
            && self.bounds.get(module).and_then(|bound| bound.kind(name)) == Some(Kind::Import)
            && matches!(
                self.imports.get(&(module, name)).map(Vec::as_slice),
                Some([("dataclasses", Some("dataclass"))])
            )
    }
}

/// A store or a delete of `__new__` or `__class__`, or a use of `__setattr__` or `__delattr__`
/// on anything but `object`: each can give a class another constructor or another metaclass.
struct PatchWatch(bool);

impl<'a> Visitor<'a> for PatchWatch {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Attribute(node) = expr {
            let attr = node.attr.as_str();
            let on_object =
                matches!(&*node.value, Expr::Name(name) if name.id.as_str() == "object");
            self.0 |= (node.ctx != ExprContext::Load && matches!(attr, "__new__" | "__class__"))
                || (matches!(attr, "__setattr__" | "__delattr__") && !on_object);
        }
        visitor::walk_expr(self, expr);
    }
}

/// True when a statement of the scan can give a class another constructor or metaclass.
pub(super) fn class_patch(scan: &Scan<'_>, modules: &[Module]) -> bool {
    scan.bounds.values().any(|bound| bound.attribute_write) || withheld(modules) || {
        let mut watch = PatchWatch(false);
        modules
            .iter()
            .for_each(|module| watch.visit_body(&module.tree.body));
        watch.0
    }
}
