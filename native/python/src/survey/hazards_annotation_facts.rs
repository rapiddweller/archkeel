// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one module for the closed-binding rule (AD-1175): scopes, bindings and writes.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Decorator, Expr, StmtClassDef};
use ruff_text_size::TextRange;

pub(super) type ScopeId = usize;

/// A flag on a scope id: the scope of a quoted annotation. Python evaluates its text in the module
/// globals and in the class of the annotation, never in the locals of a function.
pub(super) const TEXT: ScopeId = 1 << 40;

/// The names that hold or run annotations.
pub(super) const RESERVED: [&str; 4] = [
    "__annotations__",
    "__annotate__",
    "__annotate_func__",
    "__annotations_cache__",
];
pub(super) const EVALUATORS: [&str; 5] = [
    "get_type_hints",
    "get_annotations",
    "ForwardRef",
    "_eval_type",
    "evaluate_forward_ref",
];
/// A call of these gives the namespace of a module, a class or a frame: a write into it binds a
/// name by a name that the table cannot read. So does a use of `x.__dict__`.
pub(super) const NAMESPACES: [&str; 3] = ["globals", "vars", "locals"];
/// Calls that only read the namespace that they get (with the pure builtins of `globals_project`).
pub(super) const READERS: [&str; 13] = [
    "getattr",
    "hasattr",
    "sorted",
    "format",
    "iter",
    "next",
    "any",
    "all",
    "sum",
    "min",
    "max",
    "zip",
    "enumerate",
];
#[derive(PartialEq)]
pub(super) enum Kind {
    Module,
    Class,
    Function,
}

pub(super) enum Binding<'a> {
    /// `name = value`, with the scope that evaluates `value`: a `global` or `nonlocal` write puts
    /// the binding into another scope than its value belongs to.
    Value(&'a Expr, ScopeId),
    /// A class: its body scope, its decorators (each can replace the class) and their scope.
    Class(ScopeId, &'a [Decorator], ScopeId),
    /// A function and its decorators: a decorator can replace it by any value.
    Function(&'a [Decorator], ScopeId),
    /// A function, or a name that is no value of an annotation (`type X = ..`).
    Inert,
    /// `import m` binds `(m, None)`; `from m import n` binds `(m, Some(n))`.
    Import(String, Option<String>),
    Unknown,
}

pub(super) struct Scope<'a> {
    pub(super) kind: Kind,
    pub(super) parent: Option<ScopeId>,
    pub(super) names: HashMap<String, Vec<Binding<'a>>>,
    /// The class of a class scope.
    pub(super) class: Option<&'a StmtClassDef>,
    /// The modules of `from m import *`.
    pub(super) stars: Vec<String>,
    pub(super) globals: HashSet<String>,
    pub(super) nonlocals: HashSet<String>,
}

pub(super) struct Call<'a> {
    pub(super) callee: &'a Expr,
    pub(super) scope: ScopeId,
    pub(super) literal_ref: bool,
    pub(super) range: TextRange,
}

/// A write into an attribute of `receiver`: `r.a = v`, `setattr(r, "a", v)`. `attr` is `None` for a
/// computed name: it can be any attribute of the receiver.
pub(super) struct Write<'a> {
    pub(super) receiver: &'a Expr,
    pub(super) scope: ScopeId,
    pub(super) attr: Option<String>,
}

pub(super) struct Facts<'a> {
    pub(super) scopes: Vec<Scope<'a>>,
    /// Each annotation that Python evaluates, with the scope that holds it.
    pub(super) annotations: Vec<(&'a Expr, ScopeId)>,
    /// `x.a = v` and `setattr(x, "a", v)` by the attribute name, for any receiver.
    pub(super) stores: HashMap<String, Vec<Binding<'a>>>,
    /// `nonlocal` writes: `(scope of the write, name, binding)`, placed when the walk is over.
    pub(super) pending: Vec<(ScopeId, String, Binding<'a>)>,
    /// The same writes with their receiver.
    pub(super) writes: Vec<Write<'a>>,
    /// A write by a name that the table cannot read: no name of the module is closed.
    pub(super) opaque: bool,
    pub(super) evaluates: bool,
    /// `from __future__ import annotations`: each annotation is text, read like a quoted one.
    pub(super) postponed: bool,
    pub(super) reaches: Vec<TextRange>,
    pub(super) calls: Vec<Call<'a>>,
}

impl<'a> Scope<'a> {
    pub(super) fn new(
        kind: Kind,
        parent: Option<ScopeId>,
        class: Option<&'a StmtClassDef>,
    ) -> Self {
        Self {
            kind,
            parent,
            names: HashMap::new(),
            class,
            stars: Vec::new(),
            globals: HashSet::new(),
            nonlocals: HashSet::new(),
        }
    }
}

impl<'a> Facts<'a> {
    /// The scopes that bind `id` for code in `scope`. A `global` declaration reads the module, a
    /// `nonlocal` one skips its scope; a class scope is read only by its own body, and before its own assignment the outer name is read. The text of a
    /// quoted annotation reads the module and its class, in either order: `get_type_hints` of a
    /// class tries the module first, other evaluators the class first.
    pub(super) fn holders(&self, scope: ScopeId, id: &str) -> Vec<ScopeId> {
        let start = scope & !TEXT;
        let has = |at: &ScopeId| self.scopes[*at].names.contains_key(id);
        if scope & TEXT != 0 {
            let class = (self.scopes[start].kind == Kind::Class).then_some(start);
            return class.into_iter().chain([0]).filter(has).collect();
        }
        let mut holders = Vec::new();
        let mut up = Some(start);
        while let Some(at) = up {
            let scope = &self.scopes[at];
            if scope.globals.contains(id) {
                holders.extend([0].into_iter().filter(has));
                break;
            }
            let skipped =
                scope.nonlocals.contains(id) || (scope.kind == Kind::Class && at != start);
            let bound = !skipped && has(&at);
            if bound {
                holders.push(at);
            }
            // A class body reads the outer name until it assigns its own.
            if bound && scope.kind != Kind::Class {
                break;
            }
            up = scope.parent;
        }
        holders
    }

    /// The first scope of `holders`: for a read that needs one scope (a receiver of a write).
    pub(super) fn holder(&self, scope: ScopeId, id: &str) -> Option<ScopeId> {
        self.holders(scope, id).first().copied()
    }

    /// Place the `nonlocal` writes: Python binds the name in the nearest enclosing function that
    /// binds it, which can lie above a function that does not.
    pub(super) fn settle(&mut self) {
        for (scope, name, binding) in std::mem::take(&mut self.pending) {
            let above =
                std::iter::successors(self.scopes[scope].parent, |at| self.scopes[*at].parent);
            let mut functions = above.filter(|at| self.scopes[*at].kind == Kind::Function);
            let home = functions.find(|at| self.scopes[*at].names.contains_key(&name));
            let home = home
                .or_else(|| self.nearest_function(scope))
                .unwrap_or(scope);
            self.scopes[home]
                .names
                .entry(name)
                .or_default()
                .push(binding);
        }
    }

    fn nearest_function(&self, scope: ScopeId) -> Option<ScopeId> {
        let above = std::iter::successors(self.scopes[scope].parent, |at| self.scopes[*at].parent);
        let mut functions = above.filter(|at| self.scopes[*at].kind == Kind::Function);
        functions.next()
    }
}
