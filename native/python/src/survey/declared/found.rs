// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What one module declares, for the writer of the declarations and the writer of the sites.

use std::collections::HashSet;

use archkeel_facts::{Record, SymbolFact};
use ruff_python_ast::StmtFunctionDef;

use crate::module::definition::Def;

/// A function or method with a record: the scope of its sites (AD-520).
pub(crate) struct Source<'m> {
    pub node: &'m StmtFunctionDef,
    pub qualname: String,
    pub id: String,
    /// The names that the class body of a method binds: its annotations read them first.
    pub class_names: Option<HashSet<String>>,
    /// The `__slots__` entries of the class of a method; `None` when the body computes them, and
    /// empty for a function (#1523).
    pub slots: Option<HashSet<String>>,
}

/// A definition that a decorator may replace: it has no record. `wrapped` reads the form that
/// its decorators expose, when it models them (AD-782).
pub(crate) struct Decorated<'m> {
    pub def: Def<'m>,
    pub qualname: String,
    /// The names that the class body binds, for a method: its decorators and annotations read
    /// them first.
    pub class_names: Option<HashSet<String>>,
    /// The `__slots__` entries of the class of a method, as for `Source`.
    pub slots: Option<HashSet<String>>,
    /// The evidence of the definition.
    pub evidence: String,
}

/// What one module declares: its records, the sources of its sites and the top-level classes
/// that `A()` constructs.
#[derive(Default)]
pub(crate) struct Found<'m> {
    /// The index of the module in the survey.
    pub index: usize,
    pub records: Vec<Record<SymbolFact>>,
    pub sources: Vec<Source<'m>>,
    pub constructible: HashSet<String>,
    /// The definitions that a decorator may replace (AD-782).
    pub decorated: Vec<Decorated<'m>>,
}
