// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import survey of one request (`collect.collect` in the phase `imports`): the parsed
//! modules, their static imports, their file facts, the evidence, the import targets, the
//! UNKNOWN records and the coverage.
//!
//! The `stable_bindings` of a file fact are `source._stable_direct_module_bindings` (`stable`).

use std::collections::HashSet;

use archkeel_facts::envelope::{Coverage, Evidence, FileFact, Input, Target};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::pyminor::PyMinor;
use archkeel_facts::request::PythonRequest;
use archkeel_facts::vocab::ExceptionName;
use archkeel_facts::{CallFact, GapFact, ImportFact, Record, ReferenceFact, SymbolFact};
use archkeel_snapshot::Snapshot;

use crate::discover::{self, Unseen};
use crate::module::{EvidenceMap, Module};
use crate::names;
use crate::parse::{parse, ParseFailure as Failure};
use crate::source::{decode, newlines};
use binders::Binders;
use excluded::Excluded;
use failures::{early, NOT_FOUND};

pub(crate) mod binders;
pub(crate) mod bound;
mod declared;
mod excluded;
mod failures;
mod guard;
mod hazards;
mod imports;
mod layout;
mod lazy;
mod literal;
mod namespace;
mod package_body;
mod pathscope;
pub(crate) mod routes;
mod stable;
mod syspath;
mod targets;
mod uses;
mod uses_scan;
mod walks;

pub(crate) struct Survey {
    pub files: Vec<FileFact>,
    pub imports: Vec<Record<ImportFact>>,
    pub targets: Vec<Target>,
    pub unknowns: Vec<Record<GapFact>>,
    pub coverage: Coverage,
    pub evidence: Vec<Evidence>,
    /// The modules whose `__all__` the survey cannot read (`routes`).
    pub opaque_surface: HashSet<String>,
    /// The listing of each directory that a harmless `sys.path` write depends on (`syspath.rs`).
    pub listings: Vec<pathscope::Listing>,
    /// The ids of the imports that are the one plain binder of their name (`bound.rs`).
    pub sole_binders: HashSet<String>,
    /// The ids of each `from pkg import name` where `pkg` binds `name` or can give it (AD-450):
    /// the name may be the attribute or the submodule, so no route is written for it.
    pub ambiguous: HashSet<String>,
    /// The digest of each file that the survey read, from the bytes that it parsed.
    pub parsed: Vec<Input>,
    /// The symbol declarations that the modules bind once (AD-518), and their sites (AD-520).
    pub symbols: Vec<Record<SymbolFact>>,
    pub calls: Vec<Record<CallFact>>,
    pub references: Vec<Record<ReferenceFact>>,
}

/// The parsed modules of a request and their binders, as the survey reads them (the dump of
/// the definition table, AD-377).
#[cfg(feature = "dump")]
pub(crate) struct Modules {
    pub minor: PyMinor,
    pub modules: Vec<Module>,
    pub binders: Vec<Binders>,
    pub gaps: Vec<Record<GapFact>>,
}

#[cfg(feature = "dump")]
pub(crate) fn modules(request: &PythonRequest) -> Result<Modules, String> {
    let minor = request.resolver.interpreter.version.minor();
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let scope = discover::scope(
        &mut snapshot,
        &request.scope.roots,
        request.excludes_test_sources(),
    );
    let parsed = parse_unshadowed(&mut snapshot, &scope, &request.scope.namespace, minor);
    let binders = parsed
        .modules
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    Ok(Modules {
        minor,
        modules: parsed.modules,
        binders,
        gaps: parsed.gaps,
    })
}

#[expect(
    clippy::too_many_lines,
    reason = "the survey is one pipeline of passes; AD-520 adds the site pass to it"
)]
pub(crate) fn survey(request: &PythonRequest) -> Result<Survey, String> {
    let interpreter = &request.resolver.interpreter;
    let minor = interpreter.version.minor();
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let namespace = &request.scope.namespace;
    let roots = &request.scope.roots;
    let exclude = request.excludes_test_sources();
    let scope = discover::scope(&mut snapshot, roots, exclude);
    let mut parsed = parse_unshadowed(&mut snapshot, &scope, namespace, minor);
    let mut found = layout::duplicates(&mut parsed.modules);
    found.extend(layout::outside(&parsed.modules, roots));
    found.extend(layout::foreign(&scope.foreign));
    found.extend(layout::linked(&scope.linked));
    let modules = &parsed.modules;
    let binders: Vec<Binders> = modules
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let mut evidence = EvidenceMap::new();
    let (collected, written) = collect(modules, &binders, namespace, &mut evidence);
    let (mut imports, aliases) = (collected.records, collected.aliases);
    let (sole_binders, ambiguous) = (collected.sole, collected.ambiguous.clone());
    // AD-472: a proven literal import call is an import record; each other site is a gap.
    let (literals, hazards) = hazards::split(
        modules,
        &binders,
        Some(&lazy::find(modules, &binders, namespace)),
    );
    let calls = imports::literal_records(modules, &binders, namespace, &mut evidence, &literals);
    imports.extend(calls);
    imports.sort_by(|a, b| a.id.as_str().cmp(b.id.as_str()));
    let scan = pathscope::Scan::new(modules, &imports, roots, namespace);
    let (hazards, listings) = pathscope::settle(hazards, &scan, &mut snapshot);
    let mut opaque_surface: HashSet<String> = modules
        .iter()
        .zip(&binders)
        .filter(|(_, binders)| binders.all_unread)
        .map(|(module, _)| module.name.clone())
        .collect();
    opaque_surface.extend(written);
    opaque_surface.extend(uses::escaped(modules, &imports));
    let symbols = declarations(
        modules,
        &binders,
        &imports,
        (&sole_binders, &ambiguous),
        &mut evidence,
        |index, module| {
            !hazards.iter().any(|(site, _)| *site == index)
                && !opaque_surface.contains(&module.name)
        },
    );
    let files: Vec<FileFact> = modules
        .iter()
        .zip(&binders)
        .zip(&aliases)
        .map(|((module, binders), aliases)| {
            let stable = stable::bindings(module, binders, aliases, minor);
            file_fact(module, binders, stable, &mut evidence)
        })
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
    let resolved = targets::resolve(&imports, &files, &stdlib, namespace, &collected.ambiguous);
    let mut sites = resolved.gaps;
    for (index, site) in hazards {
        let module = &modules[index];
        let id = module.evidence(&mut evidence, &site.range);
        let (key, gap) = targets::site_gap(site.kind, &site.detail, &module.name, &id);
        sites.insert(key, gap);
    }
    unknowns.extend(found);
    unknowns.extend(sites.into_values());
    unknowns.extend(layout::problems(&snapshot.problems));
    let selected: HashSet<&str> = scope.selected.iter().map(String::as_str).collect();
    let coverage = Coverage {
        files_parsed: modules.len() as u64,
        files_read: parsed.files_read,
        full_scope: modules.len() == scope.selected.len() && unknowns.is_empty(),
        gaps: unknowns.clone(),
        selected_files: scope.selected.clone(),
    };
    Ok(Survey {
        targets: resolved.targets,
        files,
        imports,
        unknowns,
        coverage,
        evidence: evidence.into_values().collect(),
        opaque_surface,
        listings,
        sole_binders,
        ambiguous,
        parsed: snapshot
            .inputs()
            .into_iter()
            .filter(|input| selected.contains(input.path.as_str()))
            .collect(),
        symbols: symbols.records,
        calls: symbols.calls,
        references: symbols.references,
    })
}

/// The symbol facts of a survey: the declarations and the sites of the functions among them.
struct Symbols {
    records: Vec<Record<SymbolFact>>,
    calls: Vec<Record<CallFact>>,
    references: Vec<Record<ReferenceFact>>,
}

/// AD-518, AD-520: the declarations of each module that `admitted` keeps, then their sites. A
/// module with a hazard site or a route that another module can write has none, and each name of
/// it is absent for the model.
fn declarations(
    modules: &[Module],
    binders: &[Binders],
    imports: &[Record<ImportFact>],
    sets: (&HashSet<String>, &HashSet<String>),
    evidence: &mut EvidenceMap,
    admitted: impl Fn(usize, &Module) -> bool,
) -> Symbols {
    let mut found = Vec::new();
    let mut escapes = declared::scan_escapes(modules, binders, imports).into_iter();
    for (index, (module, binders)) in modules.iter().zip(binders).enumerate() {
        let own = escapes.next().unwrap_or_default();
        if admitted(index, module) {
            let mut item = declared::records(module, binders, own, evidence);
            item.index = index;
            found.push(item);
        }
    }
    let context = declared::Context::collect(&found, imports, sets);
    declared::attach_shapes(&mut found, (modules, binders), imports, sets);
    let (mut calls, mut references) = (Vec::new(), Vec::new());
    for item in &found {
        let (more, other) = declared::site_records(
            (&modules[item.index], &binders[item.index]),
            item,
            &context,
            evidence,
        );
        calls.extend(more);
        references.extend(other);
    }
    let records = found.into_iter().flat_map(|item| item.records).collect();
    Symbols {
        records,
        calls,
        references,
    }
}

/// The import records, after a first pass that names the modules that another module may change
/// (`uses.rs`, AD-504): such a module may bind a name of its own to a package attribute that hides
/// a submodule, so the second pass reads the written modules.
fn collect(
    modules: &[Module],
    binders: &[Binders],
    namespace: &str,
    evidence: &mut EvidenceMap,
) -> (imports::Collected, HashSet<String>) {
    let scratch = &mut EvidenceMap::new();
    let first = imports::collect_all(modules, binders, namespace, scratch, &HashSet::new());
    let written = uses::escaped(modules, &first.records);
    let collected = imports::collect_all(modules, binders, namespace, evidence, &written);
    (collected, written)
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
    minor: PyMinor,
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
/// collector does not see (over the size limit, AD-367 point 4).
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
fn parsed_module(
    rel: &str,
    raw: &[u8],
    namespace: &str,
    minor: PyMinor,
) -> Result<Module, Failure> {
    crate::source::declared_encoding(raw).map_err(|name| {
        let message = format!("source_encoding: the file declares the encoding {name}");
        early(ExceptionName::SyntaxError, &message)
    })?;
    let decode_error = || early(ExceptionName::UnicodeDecodeError, "UnicodeDecodeError");
    let text = newlines(decode(raw).ok_or_else(decode_error)?);
    let tree = parse(&text, minor)?;
    let name = names::module_for(rel, namespace, minor)
        .ok_or_else(|| early(ExceptionName::ValueError, "ValueError"))?;
    Ok(Module::new(rel.to_owned(), name, text.into_owned(), tree))
}

/// `collect._file_facts`.
fn file_fact(
    module: &Module,
    binders: &Binders,
    stable_bindings: Vec<String>,
    evidence: &mut EvidenceMap,
) -> FileFact {
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
        stable_bindings,
        blank: module.tree.body.is_empty(),
        evidence_id: EvidenceId::new(module.file_evidence(evidence)),
    }
}
