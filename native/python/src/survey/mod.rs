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
#[cfg(feature = "dump")]
use archkeel_facts::pyminor::PyMinor;
use archkeel_facts::request::PythonRequest;
use archkeel_facts::{
    CallFact, ConstructFact, GapFact, ImportFact, Record, ReferenceFact, SymbolFact,
};
use archkeel_snapshot::Snapshot;

use crate::discover;
use crate::module::{EvidenceMap, Module};
use binders::Binders;
use excluded::Excluded;
use parse_files::parse_unshadowed;

pub(crate) mod binders;
pub(crate) mod bound;
pub(crate) mod bound_kind;
mod call_count;
mod constructs;
mod copy_local;
mod declared;
mod effects;
mod excluded;
mod failures;
mod globals_locals;
mod globals_project;
mod globals_read;
mod globals_uses;
mod guard;
mod hazards;
mod imports;
mod layout;
mod lazy;
mod lazy_agree;
mod lazy_binds;
mod lazy_cover;
mod lazy_flow;
mod lazy_return;
mod lazy_shape;
mod lazy_table;
mod lazy_value;
mod lazy_writes;
mod literal;
mod namespace;
mod package_body;
mod parse_files;
mod pathscope;
pub(crate) mod routes;
mod stable;
mod syspath;
mod targets;
mod typing_count;
mod uses;
mod uses_scan;
mod uses_typing_guard;
mod value;
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
    /// The proven keys of the lazy modules (AD-654), for the routes.
    pub sources: lazy_cover::Sources,
    /// The ids of each `from pkg import name` where `pkg` binds `name` or can give it (AD-450):
    /// the name may be the attribute or the submodule, so no route is written for it.
    pub ambiguous: HashSet<String>,
    /// The digest of each file that the survey read, from the bytes that it parsed.
    pub parsed: Vec<Input>,
    /// The symbol declarations that the modules bind once (AD-518), and their sites (AD-520).
    pub symbols: Vec<Record<SymbolFact>>,
    pub calls: Vec<Record<CallFact>>,
    pub references: Vec<Record<ReferenceFact>>,
    pub constructs: Vec<Record<ConstructFact>>,
    pub broad_complete: bool,
    pub dict_complete: bool,
    pub vars_complete: bool,
    pub compare_complete: bool,
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
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let minor = request
        .resolver
        .interpreter
        .as_ref()
        .ok_or("no Python target")?
        .version
        .minor();
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
    let interpreter = request
        .resolver
        .interpreter
        .as_ref()
        .ok_or("no Python target")?;
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
    let (constructs, broad_complete, dict_complete, vars_complete, compare_complete) =
        constructs::collect(modules, &binders, &mut evidence);
    let lazy = lazy::find(modules, &binders, namespace);
    // AD-472: a proven literal import call is an import record; each other site is a gap.
    let (literals, hazards) = hazards::split(modules, &binders, Some(&lazy));
    // AD-654: a module with a hazard site keeps no proven key.
    let names = modules.iter().map(|module| module.name.as_str());
    let mut sources = lazy_cover::by_module(names, &lazy);
    for (index, _) in &hazards {
        sources.remove(&modules[*index].name);
    }
    let (collected, written) = collect(modules, &binders, namespace, &mut evidence, &mut sources);
    let (mut imports, aliases) = (collected.records, collected.aliases);
    let (sole_binders, ambiguous) = (collected.sole, collected.ambiguous.clone());
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
    opaque_surface.extend(uses::settled(modules, &imports, &mut sources));
    // AD-654: the symbol facts and the call count read a proven lazy key as its source.
    let viewed = lazy_cover::viewed(&imports, &sources);
    let symbols = declarations(
        modules,
        &binders,
        &viewed,
        (&sole_binders, &ambiguous),
        &mut evidence,
        |index, module| {
            !hazards.iter().any(|(site, _)| *site == index)
                && !opaque_surface.contains(&module.name)
        },
    );
    // AD-550: another module can write a name of an escaped module, and a hazard site can rebind
    // one, so no import of such a module is the one binder of its name.
    let withheld: HashSet<&str> = modules
        .iter()
        .enumerate()
        .filter(|(index, module)| {
            hazards.iter().any(|(site, _)| site == index) || opaque_surface.contains(&module.name)
        })
        .map(|(_, module)| module.name.as_str())
        .collect();
    for record in &mut imports {
        if withheld.contains(record.data.data().source_module.as_str()) {
            record.data.data_mut().source_binding_unique = Some(false);
        }
    }
    let files: Vec<FileFact> = modules
        .iter()
        .zip(&binders)
        .zip(&aliases)
        .map(|((module, binders), aliases)| {
            let stable = stable::bindings(module, binders, aliases, minor);
            stable::file_fact(module, binders, stable, &mut evidence)
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
        let (key, gap) = targets::hazard_gap(site, module, &id);
        sites.insert(key, gap);
    }
    unknowns.extend(found);
    unknowns.extend(sites.into_values());
    unknowns.extend(layout::problems(&snapshot.problems));
    let selected: HashSet<&str> = scope.selected.iter().map(String::as_str).collect();
    let count_context = call_count::Context::new(
        &viewed,
        &resolved.targets,
        &sole_binders,
        &ambiguous,
        &symbols.records,
        &symbols.dead_sites,
    );
    let coverage = Coverage {
        files_parsed: modules.len() as u64,
        files_read: parsed.files_read,
        full_scope: modules.len() == scope.selected.len() && unknowns.is_empty(),
        gaps: unknowns.clone(),
        measures: Some(
            modules
                .iter()
                .zip(&binders)
                .map(|(module, binders)| {
                    let mut row =
                        call_count::count(module, binders, &symbols.calls, &count_context);
                    (row.typing_positions, row.untyped_private_accesses) =
                        typing_count::count(module, binders);
                    row
                })
                .collect(),
        ),
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
        sources,
        ambiguous,
        parsed: snapshot
            .inputs()
            .into_iter()
            .filter(|input| selected.contains(input.path.as_str()))
            .collect(),
        symbols: symbols.records,
        calls: symbols.calls,
        references: symbols.references,
        constructs,
        broad_complete,
        dict_complete,
        vars_complete,
        compare_complete,
    })
}

/// The symbol facts of a survey: the declarations and the sites of the functions among them.
struct Symbols {
    records: Vec<Record<SymbolFact>>,
    calls: Vec<Record<CallFact>>,
    references: Vec<Record<ReferenceFact>>,
    dead_sites: HashSet<String>,
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
    let (mut calls, mut references, mut dead_sites) = (Vec::new(), Vec::new(), HashSet::new());
    for item in &found {
        let (more, other, dead) = declared::site_records(
            (&modules[item.index], &binders[item.index]),
            item,
            &context,
            evidence,
        );
        calls.extend(more);
        references.extend(other);
        dead_sites.extend(dead);
    }
    let records = found.into_iter().flat_map(|item| item.records).collect();
    Symbols {
        records,
        calls,
        references,
        dead_sites,
    }
}

/// The import records, after a first pass that names the modules that another module may change
/// (`uses.rs`, AD-504): such a module may bind a name of its own to a package attribute that hides
/// a submodule, so the second pass reads the written modules.
///
/// AD-654: the walk repeats until no escaped module loses the proof of its lazy keys, so the
/// ambiguous records and the escaped modules read the same proven keys.
fn collect(
    modules: &[Module],
    binders: &[Binders],
    namespace: &str,
    evidence: &mut EvidenceMap,
    sources: &mut lazy_cover::Sources,
) -> (imports::Collected, HashSet<String>) {
    let none = HashSet::new();
    loop {
        let scratch = &mut EvidenceMap::new();
        let first = imports::collect_all(modules, binders, namespace, scratch, (&none, sources));
        let written = uses::settled(modules, &first.records, sources);
        let set = (&written, &*sources);
        let collected = imports::collect_all(modules, binders, namespace, evidence, set);
        let before = sources.len();
        uses::settled(modules, &collected.records, sources);
        if sources.len() == before {
            return (collected, written);
        }
    }
}
