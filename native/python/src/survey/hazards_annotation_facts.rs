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
    /// `s: int` without a value: the name is local to the scope, but nothing is stored.
    Absent,
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
    /// The names that the scope binds with a value on a path that always runs (no `if`, loop,
    /// `try` or `match` around): only these override what a base class gives.
    pub(super) sure: HashSet<String>,
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
            sure: HashSet::new(),
        }
    }
}

impl<'a> Facts<'a> {
    /// Every scope that binds `id` and that code in `scope` can read: the scopes of its lexical
    /// chain (the module last), a class scope too. Python reads one of them, by rules that the
    /// order of the statements, `global`, `nonlocal`, a class body and the evaluator change; the
    /// rule takes all, so it holds when each is clean.
    pub(super) fn holders(&self, scope: ScopeId, id: &str) -> Vec<ScopeId> {
        let chain = std::iter::successors(Some(scope & !TEXT), |at| self.scopes[*at].parent);
        chain
            .filter(|at| self.scopes[*at].names.contains_key(id))
            .collect()
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

impl Facts<'_> {
    /// The facts of an empty module: its scope and nothing else.
    pub(super) fn new() -> Self {
        Self {
            scopes: vec![Scope::new(Kind::Module, None, None)],
            annotations: Vec::new(),
            stores: HashMap::new(),
            pending: Vec::new(),
            writes: Vec::new(),
            opaque: false,
            evaluates: false,
            postponed: false,
            reaches: Vec::new(),
            calls: Vec::new(),
        }
    }
}

/// The walk that fills `Facts` (`hazards_annotation_scopes.rs`).
pub(super) struct Build<'a, 'm> {
    pub(super) facts: Facts<'a>,
    pub(super) current: ScopeId,
    pub(super) package: &'m str,
    /// The namespace expressions that the parent only reads.
    pub(super) blessed: HashSet<TextRange>,
    /// The depth of `if`, loop, `try` and `match` bodies around the statement in its scope.
    pub(super) branch: usize,
    /// Inside the signature of a function: its annotations are evaluated.
    pub(super) signature: bool,
}
