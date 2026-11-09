// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the walk keeps of each parsed file for the cross-file passes of the records (AD-340).

use std::collections::{BTreeMap, HashMap};

use crate::definitions::Definition;
use crate::import_bindings::ImportBinding;
use crate::parse::Parsed;
use crate::source::Span;

/// What one parsed file keeps for the cross-file passes. The walk fills it only when a caller asks
/// for the records, so a plain collection pays nothing.
pub struct Kept {
    pub module: String,
    pub has_error: bool,
    /// The definitions with the qualified name of their parent inside the module.
    pub definitions: Vec<(Definition, Option<String>)>,
    /// The span of each written string and the qualified name of the definition that holds it.
    pub comparisons: Vec<(Span, Option<String>)>,
    /// The names that each import statement binds, by the line and column of the statement.
    pub bindings: HashMap<(i64, i64), Vec<ImportBinding>>,
    /// The exports of the module by name: `(declaration, export)`. Python scans the whole list for
    /// each bound name; a map keeps a file with n exports and n imports linear.
    pub exports: HashMap<String, Vec<(Span, Span)>>,
}

impl Kept {
    /// What a parsed file keeps for the records of this phase.
    pub fn from_parsed(module: &str, parsed: &Parsed) -> Self {
        let syntax = &parsed.syntax;
        let definitions = syntax
            .definitions
            .iter()
            .map(|item| (item.clone(), syntax.parent_name(item)))
            .collect();
        let comparisons = syntax
            .sites
            .comparisons
            .iter()
            .map(|item| {
                let scope = item.scope.map(|at| syntax.scopes.qualified(at));
                (item.span.clone(), scope)
            })
            .collect();
        Self::new(
            module.to_owned(),
            parsed.first_error.is_some(),
            definitions,
            comparisons,
            &syntax.import_bindings,
            &syntax.module_exports,
        )
    }

    pub fn new(
        module: String,
        has_error: bool,
        definitions: Vec<(Definition, Option<String>)>,
        comparisons: Vec<(Span, Option<String>)>,
        import_bindings: &[ImportBinding],
        module_exports: &[(String, Span, Span)],
    ) -> Self {
        let mut bindings: HashMap<(i64, i64), Vec<ImportBinding>> = HashMap::new();
        for binding in import_bindings {
            let at = (binding.span.line, binding.span.column);
            bindings.entry(at).or_default().push(binding.clone());
        }
        let mut exports: HashMap<String, Vec<(Span, Span)>> = HashMap::new();
        for (name, declaration, export) in module_exports {
            exports
                .entry(name.clone())
                .or_default()
                .push((declaration.clone(), export.clone()));
        }
        Self {
            module,
            has_error,
            definitions,
            comparisons,
            bindings,
            exports,
        }
    }
}

/// The cross-file input of the passes.
#[derive(Default)]
pub struct Pending {
    pub kept: BTreeMap<String, Kept>,
    /// The files in the order that the walk parsed them (`self.syntax` of Python).
    pub order: Vec<String>,
    /// Where each import record was written: the file, the line and the column of its statement.
    pub sites: HashMap<String, (String, i64, i64)>,
    /// The settings of the project could not be read in full (`config.partial`).
    pub partial: bool,
}
