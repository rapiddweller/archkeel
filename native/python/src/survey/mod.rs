// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT
//! The import survey of one request (`collect.collect`, phase `imports`).
//! It records parsed modules, static imports, file facts, evidence, targets, UNKNOWNs and coverage.
//!
//! The `stable_bindings` of a file fact are `source._stable_direct_module_bindings` (`stable`).
use crate::discover;
use crate::module::{EvidenceMap, Module};
use crate::requirement::Prepared;
use archkeel_facts::envelope::{Coverage, Evidence, FileFact, Input, Role, Target};
#[cfg(feature = "dump")]
use archkeel_facts::pyminor::PyMinor;
use archkeel_facts::request::PythonRequest;
use archkeel_facts::sections::SignalFact;
use archkeel_facts::{ConstructFact, GapFact, ImportFact, Record, SymbolFact};
use archkeel_snapshot::Snapshot;
use binders::Binders;
use excluded::Excluded;
use parse_files::parse_unshadowed;
use std::collections::HashSet;
pub(crate) mod binders;
pub(crate) mod bound;
pub(crate) mod bound_kind;
mod call_count;
mod class_writes;
mod constructs;
mod copy_local;
mod declared;
mod effects;
mod excluded;
mod external_loader;
mod failures;
mod globals_locals;
mod globals_project;
mod globals_read;
mod globals_uses;
mod guard;
mod hazards;
mod hazards_names;
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
mod module_scopes;
mod module_uses;
mod namespace;
mod outside;
mod package_body;
mod parse_files;
mod pathscope;
pub(crate) mod routes;
mod stable;
mod standard;
pub(crate) mod support;
mod syspath;
mod targets;
mod typing_count;
mod uses;
mod uses_scan;
mod uses_typing_guard;
mod value;
mod walks;
pub(crate) struct Survey {
    pub excluded_sources: Vec<String>,
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
    /// What the survey states about the standard library, for the premise (AD-782).
    pub standard: archkeel_facts::standard::StandardFacts,
    /// The symbol declarations that the modules bind once (AD-518), and their sites (AD-520).
    pub symbols: Vec<Record<SymbolFact>>,
    pub sites: declared::Sites,
    pub function_call_counts: Vec<(String, u64)>,
    pub constructs: Vec<Record<ConstructFact>>,
    pub signals: Vec<Record<SignalFact>>,
    /// What the survey sees of each written construct (AD-737).
    pub support: support::Support,
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
pub(crate) fn modules(prepared: &Prepared) -> Result<Modules, String> {
    let request: &PythonRequest = &prepared.request;
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let minor = prepared.interpreter.version.minor();
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
pub(crate) fn survey(prepared: &Prepared) -> Result<Survey, String> {
    let request: &PythonRequest = &prepared.request;
    let interpreter = &prepared.interpreter;
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
    // #1522: the modules that code of the repository outside the scan writes escape (AD-770).
    let mut writes = class_writes::ClassWrites::default();
    let outside = outside::written(
        &mut snapshot,
        (&mut parsed.modules, &scope.selected),
        namespace,
        &mut writes,
    );
    let settings = &request.resolver;
    let lazy_314 = crate::requirement::lazy_annotations(&mut snapshot, settings, minor.number());
    for module in &parsed.modules {
        writes.add(&module.tree);
    }
    let modules = &parsed.modules;
    let binders: Vec<Binders> = modules
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let mut evidence = EvidenceMap::new();
    let lazy = lazy::find(modules, &binders, namespace);
    let replaced = module_uses::replaces_literal_loader(modules, &binders);
    let (literals, mut hazards) = hazards::split(modules, &binders, (Some(&lazy), replaced));
    let candidates = hazards.iter().map(|(index, site)| {
        (site.kind == hazards::DYNAMIC && site.detail == "code").then_some((*index, site.range))
    });
    let class_inputs = modules.iter().zip(&binders).map(|(module, binders)| {
        let exports = !Module::is_init(module) && Binders::count(binders, "__getattr__") == Some(0);
        (
            String::as_str(&module.name),
            &module.tree,
            Binders::unique(binders),
            exports,
        )
    });
    let stable = |name: &str| !class_writes::may_write(&writes, name);
    if parsed.gaps.is_empty()
        && found.is_empty()
        && hazards::reflect::only_class_data_reads(candidates, class_inputs, &outside, stable)
    {
        hazards.clear();
    }
    // AD-654: a module with a hazard site keeps no proven key.
    let names = modules.iter().map(|module| module.name.as_str());
    let mut sources = lazy_cover::by_module(names, &lazy);
    for (index, _) in &hazards {
        sources.remove(&modules[*index].name);
    }
    let (collected, written) = collect(
        (modules, &binders),
        namespace,
        &mut evidence,
        &mut sources,
        &outside,
    );
    let (mut imports, aliases) = (collected.records, collected.aliases);
    let (sole_binders, ambiguous) = (collected.sole, collected.ambiguous.clone());
    let calls = imports::literal_records(modules, &binders, namespace, &mut evidence, &literals);
    imports.extend(calls);
    imports.sort_by(|a, b| a.id.as_str().cmp(b.id.as_str()));
    let scan = pathscope::Scan::new(modules, &imports, roots, namespace);
    let (hazards, listings) = pathscope::settle(hazards, &scan, &mut snapshot);
    let stdlib: HashSet<&str> = interpreter
        .stdlib_module_names
        .iter()
        .map(String::as_str)
        .collect();
    let read = parsed.gaps.is_empty() && found.is_empty();
    let constructs = constructs::collect(
        (modules, &binders, &imports),
        (&sole_binders, &ambiguous),
        (&writes, hazards.is_empty(), read),
        &stdlib,
        &mut evidence,
    );
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
        (modules, &binders),
        (&viewed, &imports),
        (&sole_binders, &ambiguous),
        (&writes, lazy_314),
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
    let class_namespace_safe = modules
        .iter()
        .all(|module| stable::class_inventory::namespace_safe(&module.tree))
        && hazards.is_empty()
        && opaque_surface.is_empty();
    let files: Vec<FileFact> = modules
        .iter()
        .zip(&binders)
        .zip(&aliases)
        .map(|((module, binders), aliases)| {
            let stable = stable::bindings(module, binders, aliases, minor);
            let mut file = stable::file_fact(module, binders, stable, &mut evidence);
            if !class_namespace_safe {
                file.class_inventory_empty = None;
            }
            file
        })
        .collect();
    let mut unknowns = parsed.gaps;
    if exclude {
        let excluded = Excluded::find(&mut snapshot, roots, namespace, minor);
        let bindings = package_body::package_bindings(modules);
        unknowns.extend(excluded.gaps(&imports, &bindings, scope.selected.is_empty()));
    }
    let resolved = targets::resolve(&imports, &files, &stdlib, namespace, &collected.ambiguous);
    let mut sites = resolved.gaps;
    for (index, site) in hazards {
        let module = &modules[index];
        let id = module.evidence(&mut evidence, &site.range);
        let (key, gap) = targets::hazard_gap(site, module, &id);
        sites.insert(key, gap);
    }
    // #1519: a call of a value from outside the scan with a string that names a module of it.
    for (index, range, target) in external_loader::find(modules, &stdlib, namespace) {
        let module = &modules[index];
        let id = module.evidence(&mut evidence, &range);
        let kind = external_loader::EXTERNAL_LOADER;
        let (key, gap) = targets::site_gap(kind, &target, &module.name, &id);
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
        &symbols.sites.dead,
    );
    let mut coverage = Coverage::of(
        (parsed.files_read as usize, modules.len()),
        scope.selected.clone(),
        unknowns.clone(),
    );
    // A selected module that did not parse keeps the scope from being full, gap or not.
    coverage.full_scope =
        Coverage::is_full(unknowns.len(), scope.selected.len().abs_diff(modules.len()));
    let mut function_call_counts = Vec::new();
    coverage.measures = Some(
        modules
            .iter()
            .zip(&binders)
            .map(|(module, binders)| {
                let mut row = call_count::count(
                    module,
                    binders,
                    &symbols.sites.calls,
                    &count_context,
                    &mut function_call_counts,
                );
                (row.typing_positions, row.untyped_private_accesses) =
                    typing_count::count(module, binders);
                row
            })
            .collect(),
    );
    Ok(Survey {
        function_call_counts,
        excluded_sources: scope.excluded,
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
            .inputs(|path, digest, selected| Input {
                path: path.to_owned(),
                digest: digest.to_owned(),
                role: Role::of_read(selected),
            })
            .into_iter()
            .filter(|input| selected.contains(input.path.as_str()))
            .collect(),
        standard: archkeel_facts::standard::StandardFacts {
            protocol_unchanged: constructs.protocol_unchanged,
            protocol_members: symbols.protocol_members,
            ..standard::facts(
                &writes,
                (&declared::collection_names(), &declared::FORMS),
                (symbols.wrapped, symbols.positions),
            )
        },
        symbols: symbols.records,
        sites: symbols.sites,
        signals: constructs.signals,
        support: constructs.support,
        constructs: constructs.records,
    })
}

/// The symbol facts of a survey: the declarations and the sites of the functions among them.
struct Symbols {
    records: Vec<Record<SymbolFact>>,
    /// The forms of the decorated definitions (AD-782).
    wrapped: std::collections::BTreeMap<String, archkeel_facts::standard::Wrapped>,
    /// The standard library names of each written position (#1718).
    positions: standard::Positions,
    sites: declared::Sites,
    protocol_members:
        std::collections::BTreeMap<String, (bool, archkeel_facts::standard::ProtocolMembers)>,
}

/// AD-518, AD-520: the declarations of each module that `admitted` keeps, then their sites. A
/// module with a hazard site or a route that another module can write has none, and each name of
/// it is absent for the model.
fn declarations(
    (modules, binders): (&[Module], &[Binders]),
    (imports, written): (&[Record<ImportFact>], &[Record<ImportFact>]),
    sets: (&HashSet<String>, &HashSet<String>),
    (writes, lazy_314): (&class_writes::ClassWrites, bool),
    evidence: &mut EvidenceMap,
    admitted: impl Fn(usize, &Module) -> bool,
) -> Symbols {
    let mut found = Vec::new();
    let mut escapes = declared::scan_escapes(modules, binders, imports).into_iter();
    for (index, (module, binders)) in modules.iter().zip(binders).enumerate() {
        let own = escapes.next().unwrap_or_default();
        if admitted(index, module) {
            // #1714: a class annotation reads the class namespace on 3.14, and `get_type_hints`
            // reads it for a string annotation on every version (AD-802).
            let late = lazy_314 || class_writes::future_annotations(&module.tree);
            let mut item =
                declared::records(module, binders, own, late.then_some(writes), evidence);
            item.index = index;
            found.push(item);
        }
    }
    let context = declared::Context::collect(&found, (imports, written), sets);
    let lazy = lazy_314.then_some(writes);
    declared::attach_shapes(&mut found, (modules, binders), imports, sets, lazy);
    let forms = (lazy, writes);
    let mut positions =
        declared::shape_standard::positions(&found, (modules, binders), imports, sets);
    let read = (modules, binders);
    let wrapped = declared::wrapped::forms(&found, read, imports, sets, (forms, &mut positions));
    let mut sites = declared::Sites {
        calls: Vec::new(),
        references: Vec::new(),
        dead: HashSet::new(),
        direct: Vec::new(),
    };
    for item in &found {
        let more = declared::site_records(
            (&modules[item.index], &binders[item.index]),
            item,
            &context,
            evidence,
        );
        sites.calls.extend(more.calls);
        sites.references.extend(more.references);
        sites.dead.extend(more.dead);
        sites.direct.extend(more.direct);
    }
    let protocol_members = declared::shape_standard::protocol_positions(
        &found,
        read,
        imports,
        sets,
        (evidence, writes, lazy_314),
    );
    let records = found.into_iter().flat_map(|item| item.records).collect();
    Symbols {
        records,
        wrapped,
        positions,
        sites,
        protocol_members,
    }
}

/// The import records, after a first pass that names the modules that another module may change
/// (`uses.rs`, AD-504): such a module may bind a name of its own to a package attribute that hides
/// a submodule, so the second pass reads the written modules.
///
/// AD-654: the walk repeats until no escaped module loses the proof of its lazy keys, so the
/// ambiguous records and the escaped modules read the same proven keys.
fn collect(
    (modules, binders): (&[Module], &[Binders]),
    namespace: &str,
    evidence: &mut EvidenceMap,
    sources: &mut lazy_cover::Sources,
    outside: &HashSet<String>,
) -> (imports::Collected, HashSet<String>) {
    let none = HashSet::new();
    loop {
        let scratch = &mut EvidenceMap::new();
        let first =
            imports::collect_all(modules, binders, namespace, scratch, (&none, sources), &[]);
        let mut written = uses::settled(modules, &first.records, sources);
        written.extend(outside.iter().cloned());
        let set = (&written, &*sources);
        // #1415: each use of a name through a module binding is a record of its own.
        let found = module_uses::find(modules, binders, &first.records);
        let mut collected =
            imports::collect_all(modules, binders, namespace, evidence, set, &found.uses);
        module_uses::unread_names(&mut collected.records, &found.escaped);
        let before = sources.len();
        uses::settled(modules, &collected.records, sources);
        if sources.len() == before {
            return (collected, written);
        }
    }
}
