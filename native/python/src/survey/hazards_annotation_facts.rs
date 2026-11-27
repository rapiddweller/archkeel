// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one module for the closed-binding rule (AD-1175): scopes, bindings and writes.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Expr, StmtClassDef};
use ruff_text_size::TextRange;

pub(super) type ScopeId = usize;

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
/// Calls that only read the namespace that they get.
pub(super) const READERS: [&str; 24] = [
    "getattr",
    "hasattr",
    "isinstance",
    "issubclass",
    "len",
    "sorted",
    "list",
    "dict",
    "set",
    "tuple",
    "frozenset",
    "print",
    "repr",
    "str",
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
pub(super) const READ_METHODS: [&str; 5] = ["get", "items", "keys", "values", "copy"];
#[derive(PartialEq)]
pub(super) enum Kind {
    Module,
    Class,
    Function,
}

pub(super) enum Binding<'a> {
    /// `name = value`.
    Value(&'a Expr),
    Class(ScopeId),
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
    /// The same writes with their receiver.
    pub(super) writes: Vec<Write<'a>>,
    /// A write by a name that the table cannot read: no name of the module is closed.
    pub(super) opaque: bool,
    pub(super) evaluates: bool,
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
