// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the walk keeps of each parsed file for the cross-file passes of the records (AD-340).

use std::collections::{BTreeMap, HashMap, HashSet};

use crate::definitions::{Definition, Scopes};
use crate::exports::{ExportBinding, TypeExports};
use crate::import_bindings::ImportBinding;
use crate::kept_script::ScriptFile;
use crate::parse::Parsed;
use crate::script_records::ScriptFacts;
use crate::site_names::NameIndex;
use crate::sites::Sites;
use crate::source::{FileSite, Span};

/// What one parsed file keeps for the cross-file passes. The walk fills it only when a caller asks
/// for the records, so a plain collection pays nothing.
pub(crate) struct Kept {
    pub module: String,
    pub has_error: bool,
    /// The definitions and their parent scope indices.
    pub definitions: Vec<Definition>,
    /// The span of each written string and the qualified name of the definition that holds it.
    pub comparisons: Vec<(Span, Option<String>)>,
    /// The names that each import statement binds, by the line and column of the statement.
    pub bindings: HashMap<(i64, i64), Vec<ImportBinding>>,
    /// The exports of the module by name: `(declaration, export)`. Python scans the whole list for
    /// each bound name; a map keeps a file with n exports and n imports linear.
    pub exports: HashMap<String, Vec<(Span, Span)>>,
    pub type_exports: TypeExports,
    /// The sites of the file and the scopes that hold them (PR 4.3a-3c).
    pub sites: Sites,
    pub scopes: Scopes,
    /// The names that the module assigns outside every function (`rebound_names`).
    pub rebound: HashSet<String>,
    pub written_root_names: HashSet<String>,
    pub ambiguous_root_names: HashSet<String>,
    /// The text that the byte ranges of the sites point into.
    pub text: Vec<u8>,
    /// The question "does a scope hide this name" for the sites of the file.
    pub shadow: NameIndex,
    /// The script facts and the flags that the script analysis reads.
    pub script: ScriptFile,
    /// AD-778: the gap reason and the longest site, when the records of the file would copy too
    /// many bytes. The file keeps no site then.
    pub record_refusal: Option<(String, Span)>,
    /// The names of the classes whose members a form of the file can change (AD-747).
    pub patched: std::collections::BTreeSet<String>,
}

impl Kept {
    /// What a parsed file keeps for the records of this phase.
    pub(crate) fn from_parsed(
        module: &str,
        parsed: &mut Parsed,
        text: &str,
        script: ScriptFile,
    ) -> Self {
        let syntax = &mut parsed.syntax;
        let definitions = std::mem::take(&mut syntax.definitions);
        let comparisons = syntax
            .sites
            .comparisons
            .iter()
            .map(|item| {
                let scope = item.scope.map(|at| Scopes::qualified(&syntax.scopes, at));
                (item.span.clone(), scope)
            })
            .collect();
        let mut kept = Self::new(
            module.to_owned(),
            parsed.first_error.is_some(),
            definitions,
            comparisons,
            &syntax.import_bindings,
            &syntax.module_exports,
            (
                std::mem::take(&mut syntax.written_root_names),
                std::mem::take(&mut syntax.ambiguous_root_names),
            ),
        );
        kept.rebound = syntax.rebound_names.iter().cloned().collect();
        kept.patched = std::mem::take(&mut syntax.patched);
        kept.type_exports = std::mem::take(&mut syntax.type_exports);
        kept.sites = std::mem::take(&mut syntax.sites);
        kept.record_refusal = crate::site_charge::over(&kept.sites.sites);
        if kept.record_refusal.is_some() {
            kept.sites.sites.clear();
        }
        kept.scopes = std::mem::take(&mut syntax.scopes);
        kept.shadow = kept.sites.names.index(text.as_bytes());
        for site in &mut kept.sites.sites {
            let named = site.name.filter(|_| site.receiver.is_none());
            site.local = named.is_some_and(|name| {
                kept.shadow
                    .locally(&name.decode(text.as_bytes()), name.start)
            });
        }
        for definition in &mut kept.definitions {
            for base in &mut definition.bases {
                base.shadowed = kept.shadow.locally(&base.name, base.start);
            }
        }
        kept.text = kept.sites.retain_text(text.as_bytes());
        kept.script = script;
        kept
    }

    pub(crate) fn new(
        module: String,
        has_error: bool,
        definitions: Vec<Definition>,
        comparisons: Vec<(Span, Option<String>)>,
        import_bindings: &[ImportBinding],
        module_exports: &[ExportBinding],
        root_names: (HashSet<String>, HashSet<String>),
    ) -> Self {
        let mut bindings: HashMap<(i64, i64), Vec<ImportBinding>> = HashMap::new();
        for binding in import_bindings {
            let at = (binding.span.line, binding.span.column);
            bindings.entry(at).or_default().push(binding.clone());
        }
        let mut exports: HashMap<String, Vec<(Span, Span)>> = HashMap::new();
        for ExportBinding {
            name,
            declaration,
            export,
        } in module_exports
        {
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
            type_exports: TypeExports::default(),
            sites: Sites::default(),
            scopes: Scopes::default(),
            rebound: HashSet::new(),
            written_root_names: root_names.0,
            ambiguous_root_names: root_names.1,
            text: Vec::new(),
            shadow: NameIndex::default(),
            script: ScriptFile::default(),
            record_refusal: None,
            patched: std::collections::BTreeSet::new(),
        }
    }
}

/// The cross-file input of the passes.
#[derive(Default)]
pub(crate) struct Pending {
    pub kept: BTreeMap<String, Kept>,
    /// The files in the order that the walk parsed them (`self.syntax` of Python).
    pub order: Vec<String>,
    /// Where each import record was written: the file, the line and the column of its statement.
    pub(crate) sites: HashMap<String, FileSite>,
    /// The settings of the project could not be read in full (`config.partial`).
    pub partial: bool,
    /// The requested bundler mode is active for these compiler settings.
    pub bundler: bool,
    /// What the script analysis found (`script_deps.rs`).
    pub script: ScriptFacts,
    /// Some file can use a browser global, so the reply declares `script-globals-v1`.
    pub dependency_scope: bool,
}
