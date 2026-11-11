// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import survey of one request (`collect.collect` in the phase `imports`), slice 1c-2a:
//! the parsed modules, their static imports, their file facts and the evidence of both.
//!
//! The failure records, the gaps, the import targets and the reply follow in slice 1c-2b. The
//! `stable_bindings` of a file fact need the member analysis of `source.py` and are empty here.

use std::collections::HashSet;

use archkeel_facts::envelope::{Evidence, FileFact};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::request::PythonRequest;
use archkeel_facts::{ImportFact, Record};
use archkeel_snapshot::Snapshot;

use crate::parse::parse;
use crate::source::decode;
use crate::{discover, names};
use binders::Binders;
use module::{EvidenceMap, Module};

mod binders;
mod imports;
mod module;

pub struct Survey {
    pub files: Vec<FileFact>,
    pub imports: Vec<Record<ImportFact>>,
    pub evidence: Vec<Evidence>,
}

/// The minor version of `platform.python_version()`, for example 12 of `3.12.10`.
pub fn minor(version: &str) -> Result<u32, String> {
    version
        .split('.')
        .nth(1)
        .and_then(|minor| minor.parse().ok())
        .ok_or_else(|| format!("the interpreter version {version} has no minor version"))
}

pub fn survey(request: &PythonRequest) -> Result<Survey, String> {
    let minor = minor(&request.resolver.interpreter.version)?;
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let namespace = &request.scope.namespace;
    let roots = &request.scope.roots;
    let selected = discover::scope(&mut snapshot, roots, request.excludes_test_sources()).selected;
    let modules = parse_unshadowed(&mut snapshot, &selected, namespace, minor);
    let binders: Vec<Binders> = modules
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let mut evidence = EvidenceMap::new();
    let imports = imports::collect(&modules, &binders, namespace, &mut evidence);
    let files = modules
        .iter()
        .zip(&binders)
        .map(|(module, binders)| file_fact(module, binders, &mut evidence))
        .collect();
    Ok(Survey {
        files,
        imports,
        evidence: evidence.into_values().collect(),
    })
}

/// `parse_unshadowed`: the modules of the selected files that the import system can reach and
/// that read, decode, parse and have a module name, in the order of the selection.
fn parse_unshadowed(
    snapshot: &mut Snapshot,
    selected: &[String],
    namespace: &str,
    minor: u32,
) -> Vec<Module> {
    let shadowed: HashSet<String> = names::shadowed(selected, namespace, minor)
        .into_iter()
        .map(|item| item.file)
        .collect();
    let mut modules = Vec::new();
    for rel in selected.iter().filter(|rel| !shadowed.contains(*rel)) {
        let Some(raw) = snapshot.read(rel) else {
            continue;
        };
        let Some(text) = decode(&raw) else {
            continue;
        };
        let Ok(tree) = parse(text, minor) else {
            continue;
        };
        let Some(name) = names::module_for(rel, namespace, minor) else {
            continue;
        };
        modules.push(Module::new(rel.clone(), name, text.to_owned(), tree));
    }
    modules
}

/// `collect._file_facts` without `stable_bindings` (slice 1c-2b).
fn file_fact(module: &Module, binders: &Binders, evidence: &mut EvidenceMap) -> FileFact {
    let mut exports: Vec<String> = binders.all_exports.iter().cloned().collect();
    exports.sort();
    FileFact {
        id: FactId::new(stable_id("FILE", &[Part::Text(&module.name)])),
        rel_path: module.rel.clone(),
        module: ModuleName::new(module.name.as_str()),
        package: PackageName::new(module.package.as_str()),
        all_exports: exports,
        all_literal: binders.all_literal,
        compatibility_logic_free: binders.logic_free,
        stable_bindings: Vec::new(),
        blank: module.tree.body.is_empty(),
        evidence_id: EvidenceId::new(module.file_evidence(evidence)),
    }
}
