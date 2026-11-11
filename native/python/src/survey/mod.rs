// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import survey of one request (`collect.collect` in the phase `imports`): the parsed
//! modules, their static imports, their file facts, the evidence, the import targets, the
//! UNKNOWN records and the coverage.
//!
//! The `stable_bindings` of a file fact need the member analysis of `source.py`. They follow in
//! slice 1c-2c; until then the binary refuses each request, so no reply carries the empty value.

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::{Coverage, Evidence, FileFact, Target};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::request::PythonRequest;
use archkeel_facts::vocab::ExceptionName;
use archkeel_facts::{GapFact, ImportFact, Record};
use archkeel_snapshot::Snapshot;

use crate::discover::{self, Unseen};
use crate::names;
use crate::parse::{parse, Failure};
use crate::source::decode;
use binders::Binders;
use excluded::Excluded;
use failures::{early, NOT_FOUND};
use module::{EvidenceMap, Module};

mod binders;
mod excluded;
mod failures;
mod imports;
mod module;

pub struct Survey {
    pub files: Vec<FileFact>,
    pub imports: Vec<Record<ImportFact>>,
    pub targets: Vec<Target>,
    pub unknowns: Vec<Record<GapFact>>,
    pub coverage: Coverage,
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
    let interpreter = &request.resolver.interpreter;
    let minor = minor(&interpreter.version)?;
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let namespace = &request.scope.namespace;
    let roots = &request.scope.roots;
    let exclude = request.excludes_test_sources();
    let scope = discover::scope(&mut snapshot, roots, exclude);
    let parsed = parse_unshadowed(&mut snapshot, &scope, namespace, minor);
    let modules = &parsed.modules;
    let binders: Vec<Binders> = modules
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let mut evidence = EvidenceMap::new();
    let imports = imports::collect(modules, &binders, namespace, &mut evidence);
    let files: Vec<FileFact> = modules
        .iter()
        .zip(&binders)
        .map(|(module, binders)| file_fact(module, binders, &mut evidence))
        .collect();
    let mut unknowns = parsed.gaps;
    if exclude {
        let excluded = Excluded::find(&mut snapshot, roots, namespace, minor);
        let bindings = imports::package_bindings(modules);
        unknowns.extend(excluded.gaps(&imports, &bindings, scope.selected.is_empty()));
    }
    let stdlib: HashSet<&str> = interpreter
        .stdlib_module_names
        .iter()
        .map(String::as_str)
        .collect();
    let coverage = Coverage {
        files_parsed: modules.len() as u64,
        files_read: parsed.files_read,
        full_scope: modules.len() == scope.selected.len() && unknowns.is_empty(),
        gaps: unknowns.clone(),
        selected_files: scope.selected.clone(),
    };
    Ok(Survey {
        targets: targets(&imports, &files, &stdlib),
        files,
        imports,
        unknowns,
        coverage,
        evidence: evidence.into_values().collect(),
    })
}

struct Parsed {
    modules: Vec<Module>,
    /// The failures in the order of the selection, the shadowed modules and the unseen files.
    gaps: Vec<Record<GapFact>>,
    files_read: u64,
}

/// `parse_unshadowed`: the modules of the selected files that the import system can reach and
/// that read, decode, parse and have a module name; a record for each other file.
fn parse_unshadowed(
    snapshot: &mut Snapshot,
    scope: &discover::Scope,
    namespace: &str,
    minor: u32,
) -> Parsed {
    let shadowed = names::shadowed(&scope.selected, namespace, minor);
    let skipped: HashSet<&str> = shadowed.iter().map(|item| item.file.as_str()).collect();
    let mut parsed = Parsed {
        modules: Vec::new(),
        gaps: Vec::new(),
        files_read: 0,
    };
    let mut unseen: Vec<Unseen> = scope
        .unseen
        .iter()
        .filter(|item| !matches!(item, Unseen::Missing(_)))
        .cloned()
        .collect();
    for rel in scope
        .selected
        .iter()
        .filter(|rel| !skipped.contains(rel.as_str()))
    {
        let Some(raw) = snapshot.read(rel) else {
            match unread(snapshot, rel) {
                Ok(failure) => parsed.gaps.push(failures::failure(rel, &failure)),
                Err(item) => unseen.push(item),
            }
            continue;
        };
        parsed.files_read += 1;
        match parsed_module(rel, &raw, namespace, minor) {
            Ok(module) => parsed.modules.push(module),
            Err(failure) => parsed.gaps.push(failures::failure(rel, &failure)),
        }
    }
    parsed.gaps.extend(shadowed.iter().map(failures::shadowed));
    for item in &unseen {
        let (Unseen::NotUtf8(rel)
        | Unseen::Oversized(rel)
        | Unseen::Missing(rel)
        | Unseen::Special(rel)) = item;
        let reason = item
            .reason(snapshot)
            .unwrap_or_else(|| format!("Source unseen: {rel}"));
        parsed.gaps.push(failures::unseen(rel, &reason));
    }
    parsed
}

/// Why a selected file did not read: the failure of Python, or a file that the native
/// collector does not see (over the size limit, AD-365 point 4).
fn unread(snapshot: &mut Snapshot, rel: &str) -> Result<Failure, Unseen> {
    if snapshot.size_gap(rel).is_some() {
        return Err(Unseen::Oversized(rel.to_owned()));
    }
    if snapshot.is_dir(rel) {
        return Ok(early(ExceptionName::IsADirectoryError, "Is a directory"));
    }
    if snapshot.real(rel).is_none() {
        return Ok(early(ExceptionName::FileNotFoundError, NOT_FOUND));
    }
    Ok(early(
        ExceptionName::OsError,
        "the native collector cannot read the file",
    ))
}

/// Decode, parse and name one file, in the order of `parse_sources`.
fn parsed_module(rel: &str, raw: &[u8], namespace: &str, minor: u32) -> Result<Module, Failure> {
    let decode_error = || early(ExceptionName::UnicodeDecodeError, "UnicodeDecodeError");
    let text = decode(raw).ok_or_else(decode_error)?;
    let tree = parse(text, minor)?;
    let name = names::module_for(rel, namespace, minor)
        .ok_or_else(|| early(ExceptionName::ValueError, "ValueError"))?;
    Ok(Module::new(rel.to_owned(), name, text.to_owned(), tree))
}

/// `collect._file_facts` without `stable_bindings` (slice 1c-2c).
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

/// `collect._import_targets`: a selected module, a module of the standard library of the
/// interpreter in the request, an external package, or unresolved.
fn targets(
    imports: &[Record<ImportFact>],
    files: &[FileFact],
    stdlib: &HashSet<&str>,
) -> Vec<Target> {
    let by_module: HashMap<&str, &str> = files
        .iter()
        .map(|file| (file.module.as_str(), file.rel_path.as_str()))
        .collect();
    imports
        .iter()
        .map(|import| {
            let data = import.data.data();
            let import_id = import.id.clone();
            let module = data.target_module.as_str();
            let package = data.target_package.as_str();
            if let Some(file) = by_module.get(module) {
                Target::Local {
                    import_id,
                    module: data.target_module.clone(),
                    file: (*file).to_owned(),
                    runtime_file: None,
                    declaration_file: None,
                }
            } else if stdlib.contains(module) || module == "builtins" {
                Target::Builtin {
                    import_id,
                    name: module.to_owned(),
                }
            } else if !package.is_empty() {
                Target::External {
                    import_id,
                    package: data.target_package.clone(),
                }
            } else {
                Target::Unresolved {
                    import_id,
                    specifier: module.to_owned(),
                    reason: "module source not found".to_owned(),
                }
            }
        })
        .collect()
}
