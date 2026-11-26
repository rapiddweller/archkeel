// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The part of the model that only the reply and the settings give (slices S1 to S3): the
//! modules, packages, imports, edges, measures and cycles. It needs no contract, so a run whose
//! contract the core cannot use yet still has its rows. The core derives it one time per run.
//! The declared reach of the trojan horses of the root contract (AD-664) is the one contract input: it
//! adds declared imports, so the edges and the cycles read them.
//! The macro bodies are typed rows of the split (`MacroBody`): the fan counts of the modules
//! read them while the graph is derived, and nothing reads them after.

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::{Facts, Target};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName};
use archkeel_facts::profile_traits::AnalysisCapabilities;
use archkeel_facts::{CallFact, FactData, Section, SymbolFact};
use archkeel_store::Ingested;

use crate::constructs::Constructs;
use crate::coverage::{self, Incomplete};
use crate::cycles::{self, Cycle};
use crate::door_reach::{self, TrojanHorses};
use crate::edges::{self, Edge, Level};
use crate::gap_class::{self, Class};
use crate::ids::{Id, ModuleId, PackageId, Table};
use crate::imports::{self, Import};
use crate::modules::{self, Module, Package};
use crate::needs::Needs;
use crate::observed::{self, Observed};
use crate::reason::Reason;
use crate::settings::{Producer, Settings};
use crate::topology::{self, Measure};

/// The reply part of the model of one run.
#[derive(Debug)]
pub struct Graph {
    modules: Table<ModuleId, Module>,
    packages: Table<PackageId, Package>,
    incomplete: Option<Incomplete>,
    gaps: Vec<crate::gaps::CoverageGap>,
    settings: Settings,
    imports: Vec<Import>,
    /// The names that the records of the reply bind or declare (AD-668, AD-1048).
    names: crate::imports::Names,
    /// The source and target module of each resolved macro body (AD-670).
    macro_bodies: Vec<(String, String)>,
    /// The public module-level items, when a rule of the run reads them (AD-670).
    published: Option<Vec<crate::published_items::PublicItem>>,
    module_edges: Vec<Edge>,
    package_edges: Vec<Edge>,
    module_measures: Vec<Measure>,
    package_measures: Vec<Measure>,
    symbol_counts: Option<Vec<usize>>,
    cycles: Vec<Cycle>,
    observed: Observed,
    builtins: Vec<String>,
    constructs: Constructs,
    /// The symbol table, when a need of the run reads it (AD-512).
    symbols: Option<crate::symbols::Symbols>,
    /// The records that `boundary_types` reads, when the run needs them and the collector writes
    /// shapes (AD-550).
    boundary: Option<crate::boundary_facts::BoundaryFacts>,
    placement: Option<Vec<crate::placement_facts::Class>>,
    exact_calls: Option<CallInventory>,
    /// The declared reach of the trojan horse sites (AD-664).
    trojan_horses: TrojanHorses,
}

impl Graph {
    /// Derive the reply part of a model from a validated reply and the settings of the shell.
    pub fn derive(reply: &Ingested, settings: Settings) -> Result<Graph, Reason> {
        Self::derive_for(reply, settings, &Needs::default())
    }

    /// Derive the reply part for a run with `needs`: a need that reads the symbols adds the
    /// symbol table (AD-512), when the collector of the profile states symbol facts. Without a need,
    /// the reply part is the same as `derive` gives.
    pub fn derive_for(
        reply: &Ingested,
        settings: Settings,
        needs: &Needs,
    ) -> Result<Graph, Reason> {
        let facts = admitted(reply, &settings)?;
        let live = settings.producer() == Producer::Trusted;
        let mut graph = Self::from_facts(
            facts,
            reply.analysis_capabilities(),
            settings,
            needs.trojan_horses(),
        )?;
        if needs.symbols() && graph.observed.analysis.symbol_facts {
            graph.symbols = Some(crate::symbol_table::derive(
                facts,
                &graph.modules,
                graph.observed.analysis.symbol_sites,
            ));
        }
        if needs.published() {
            graph.published = Some(crate::published_items::items(facts));
        }
        if needs.boundary() && graph.observed.analysis.type_shapes {
            graph.boundary = Some(crate::boundary_facts::BoundaryFacts::derive(facts));
        }
        if needs.placement() && graph.observed.analysis.symbol_facts {
            graph.placement = Some(crate::placement_facts::classes(facts));
        }
        if live && needs.call_owner() {
            graph.exact_calls = direct_calls(facts, reply.call_owners());
        }
        Ok(graph)
    }

    pub(crate) fn from_facts(
        facts: &Facts,
        analysis: AnalysisCapabilities,
        settings: Settings,
        declared: &[archkeel_contract::TrojanHorseReach],
    ) -> Result<Graph, Reason> {
        let settings = settings.bound(&facts.adapter.name, facts.profile.as_str());
        let (modules, packages) = modules::tables(&facts.files)?;
        // AD-664: the declared reach of the trojan horses; a declared gap names no unresolved import.
        let mut trojan_horses = door_reach::matched(declared, facts, &settings);
        let mut split = imports::split(facts, analysis.target_marks, |gap| {
            trojan_horses.of_gap(gap).is_some()
        });
        split.imports.extend(trojan_horses.take_imports());
        split.names.declared = crate::published_items::declared(facts);
        let (module_edges, package_edges) =
            edges::both(&facts.files, &split.imports, settings.namespace());
        let module_measured = topology::modules(&modules, &module_edges, &split.macro_bodies);
        let package_measured = topology::packages(&packages, &package_edges);
        let cycles = cycles::cycles(
            &modules,
            &packages,
            (&module_measured, &module_edges),
            (&package_measured, &package_edges),
        );
        // AD-564: each gap has one class; the state, the gap rows and the scope facts read it.
        let names: std::collections::HashSet<&str> =
            modules.iter().map(|(_, module)| module.name()).collect();
        let classes = gap_class::classes(&facts.coverage, |name| names.contains(name));
        let whole = classes.iter().filter(|c| **c == Class::Whole).count();
        let live_target = match settings.producer() {
            Producer::Trusted if facts.profile_limits.is_some() => facts.runtime.target_source,
            Producer::Trusted | Producer::External => None,
        };
        let mut observed = observed::observed(facts, analysis, &classes, live_target);
        observed.effect_gaps = door_reach::narrowed(&trojan_horses, observed.effect_gaps);
        let gaps = crate::gaps::coverage_gaps(&facts.coverage, &classes);
        drop(names);
        let constructs = Constructs::derive(facts, settings.producer() == Producer::Trusted)?;
        Ok(Graph {
            symbol_counts: symbol_counts(facts, &modules),
            modules,
            packages,
            incomplete: coverage::incomplete(&facts.coverage, whole, split.unknown),
            gaps,
            settings,
            imports: split.imports,
            names: split.names,
            macro_bodies: split
                .macro_bodies
                .iter()
                .map(|body| {
                    (
                        body.source_module().to_owned(),
                        body.target_module().to_owned(),
                    )
                })
                .collect(),
            published: None,
            module_edges,
            package_edges,
            module_measures: module_measured.measures,
            package_measures: package_measured.measures,
            cycles,
            observed,
            builtins: builtins(facts),
            constructs,
            symbols: None,
            boundary: None,
            placement: None,
            exact_calls: None,
            trojan_horses,
        })
    }

    /// The declared reach of the trojan horse sites, matched to the trojan horses of the reply (AD-664).
    pub fn trojan_horses(&self) -> &TrojanHorses {
        &self.trojan_horses
    }

    pub(crate) fn exact_calls(&self) -> Option<&CallInventory> {
        self.exact_calls.as_ref()
    }

    /// The modules of the reply, in the order of the reply.
    pub fn modules(&self) -> &Table<ModuleId, Module> {
        &self.modules
    }

    /// The packages of the reply, in name order.
    pub fn packages(&self) -> &Table<PackageId, Package> {
        &self.packages
    }

    /// What the reply proves not seen, if anything. It can only give UNKNOWN, never PASS.
    pub fn incomplete(&self) -> Option<Incomplete> {
        self.incomplete
    }

    /// The coverage gaps of the reply, in its order (AD-484).
    pub fn coverage_gaps(&self) -> &[crate::gaps::CoverageGap] {
        &self.gaps
    }

    /// The settings of the shell: the namespace and the standard library of the profile.
    pub fn settings(&self) -> &Settings {
        &self.settings
    }

    /// The resolved imports that are not macro bodies, in the order of the reply.
    pub fn imports(&self) -> &[Import] {
        &self.imports
    }

    pub(crate) fn imports_for_symbol_rule(
        &self,
        source_names_only: bool,
    ) -> impl Iterator<Item = &Import> {
        // A saved reply does not distinguish a written name from an inferred receiver.
        let live = self.settings.producer() == Producer::Trusted;
        self.imports
            .iter()
            .filter(move |import| !source_names_only || live && !import.inferred_receiver)
    }

    /// The source and target module of each resolved macro body (AD-670).
    pub(crate) fn macro_bodies(&self) -> &[(String, String)] {
        &self.macro_bodies
    }

    /// The public module-level items, when a rule of the run reads them (AD-670).
    pub(crate) fn published(&self) -> Option<&[crate::published_items::PublicItem]> {
        self.published.as_deref()
    }

    /// Whether a record binds `symbol` under another name (`use a::Profile as Lang`, AD-668).
    pub(crate) fn renamed(&self, symbol: &str) -> bool {
        self.names.renamed(symbol)
    }

    /// Whether a module-level symbol of this name lies in a module that `of_target` accepts
    /// (AD-1048).
    pub(crate) fn declared(&self, of_target: impl Fn(&str) -> bool, symbol: &str) -> bool {
        self.names.declared(of_target, symbol)
    }

    /// The edges of one level, in the order of their (source, target) pairs.
    pub fn edges(&self, level: Level) -> &[Edge] {
        match level {
            Level::Module => &self.module_edges,
            Level::Package => &self.package_edges,
        }
    }

    /// The fan counts and the rank of a module.
    pub fn module_measure(&self, module: ModuleId) -> Measure {
        topology::of(&self.module_measures, module)
    }

    /// The fan counts and the rank of a package.
    pub fn package_measure(&self, package: PackageId) -> Measure {
        topology::of(&self.package_measures, package)
    }

    /// The number of symbols of a module, or `None` when the reply has no symbols section.
    pub fn symbol_count(&self, module: ModuleId) -> Option<usize> {
        let counts = self.symbol_counts.as_ref()?;
        Some(counts.get(module.index()).copied().unwrap_or(0))
    }

    /// The module and package cycles, sorted by id.
    pub fn cycles(&self) -> &[Cycle] {
        &self.cycles
    }

    /// The original construct inventory and actual named owners of the reply.
    pub(crate) fn constructs(&self) -> &Constructs {
        &self.constructs
    }

    /// The symbol table, when a need of the run reads it (AD-512).
    /// The records that `boundary_types` reads, when the run has them (AD-550).
    pub(crate) fn boundary(&self) -> Option<&crate::boundary_facts::BoundaryFacts> {
        self.boundary.as_ref()
    }

    pub(crate) fn placement(&self) -> Option<&[crate::placement_facts::Class]> {
        self.placement.as_deref()
    }

    pub(crate) fn symbols(&self) -> Option<&crate::symbols::Symbols> {
        self.symbols.as_ref()
    }

    /// The language name of the collector that read the modules, as the collector states it
    /// (AD-494). The model compares no name and maps none.
    pub fn language(&self) -> &'static str {
        self.observed.analysis.language
    }

    /// What the reply says about its own scope (slice S4).
    pub(crate) fn observed(&self) -> &Observed {
        &self.observed
    }

    /// The names of the builtin import targets of the reply.
    pub(crate) fn builtins(&self) -> &[String] {
        &self.builtins
    }
}

/// The names of the builtin import targets (`BuiltinTarget.name`).
/// The call site, module, lexical scope, target and evidence.
pub type ExactCall = (FactId, String, String, String, Vec<EvidenceId>);

#[derive(Debug)]
pub(crate) struct CallInventory {
    pub(crate) calls: Vec<ExactCall>,
    pub(crate) targets: HashSet<String>,
    pub(crate) complete: HashSet<String>,
    pub(crate) bodies: HashMap<String, u64>,
    pub(crate) constructors: HashSet<FactId>,
    pub(crate) actuals: HashMap<FactId, Vec<archkeel_facts::envelope::WrittenActual>>,
    pub(crate) formals: HashMap<String, Vec<archkeel_facts::nested::Parameter>>,
}

fn direct_calls(
    facts: &Facts,
    constructed: Option<&archkeel_store::CallOwners>,
) -> Option<CallInventory> {
    let live = facts.direct_calls.as_ref()?;
    let sites: HashSet<&FactId> = live.iter().map(|(site, _, _, _)| site).collect();
    let mut calls = Vec::new();
    let mut counts: HashMap<&str, u64> = HashMap::new();
    let rows = facts.sections.iter().filter_map(|section| match section {
        Section::Calls(rows) => Some(rows),
        _ => None,
    });
    for row in rows.flatten().filter(|row| sites.contains(&row.id)) {
        let CallFact::Calls(call) = &row.data else {
            continue;
        };
        let [target] = Vec::as_slice(&call.targets) else {
            continue;
        };
        *counts.entry(call.source_module.as_str()).or_default() += 1;
        calls.push((
            row.id.clone(),
            ModuleName::as_str(&call.source_module).to_owned(),
            call.source_scope.clone(),
            target.clone(),
            row.evidence_ids.clone(),
        ));
    }
    let mut targets = direct_targets(facts);
    let mut constructors = HashSet::new();
    if let Some(owners) = constructed {
        targets.extend(owners.targets().iter().cloned());
        let witnessed: &[archkeel_store::OwnedCall] = owners.calls();
        for call in witnessed {
            *counts.entry(&call.module).or_default() += 2;
            constructors.insert(call.site.clone());
            calls.push((
                call.site.clone(),
                call.module.clone(),
                call.scope.clone(),
                call.target.clone(),
                call.evidence.clone(),
            ));
        }
    }
    let complete = facts.coverage.measures.iter().flatten().filter_map(|row| {
        let count = counts.get(row.module.as_str()).copied().unwrap_or(0);
        (count == row.calls_total).then(|| ModuleName::as_str(&row.module).to_owned())
    });
    let bodies = facts
        .function_call_counts
        .iter()
        .flatten()
        .cloned()
        .collect();
    Some(CallInventory {
        calls,
        targets,
        constructors,
        complete: complete.collect(),
        bodies,
        actuals: live
            .iter()
            .filter_map(|(site, _, _, arguments)| Some((site.clone(), arguments.as_ref()?.clone())))
            .collect(),
        formals: direct_formals(facts),
    })
}

fn direct_formals(facts: &Facts) -> HashMap<String, Vec<archkeel_facts::nested::Parameter>> {
    facts
        .sections
        .iter()
        .filter_map(|section| match section {
            Section::Symbols(rows) => Some(rows),
            _ => None,
        })
        .flatten()
        .filter_map(|row| match &row.data {
            SymbolFact::Function(function)
                if function.source_binding_unique == Some(true)
                    && Vec::is_empty(&function.decorators)
                    && function.lexical_parent_id.is_none()
                    && function.signature_complete == Some(true) =>
            {
                Some((function.qualified_name.clone(), function.parameters.clone()))
            }
            _ => None,
        })
        .collect()
}

fn direct_targets(facts: &Facts) -> HashSet<String> {
    let rows = facts.sections.iter().filter_map(|section| match section {
        Section::Symbols(rows) => Some(rows),
        _ => None,
    });
    rows.flatten()
        .filter_map(|row| match &row.data {
            SymbolFact::Function(function)
                if function.source_binding_unique == Some(true)
                    && Vec::is_empty(&function.decorators)
                    && function.lexical_parent_id.is_none() =>
            {
                Some(function.qualified_name.clone())
            }
            _ => None,
        })
        .collect()
}

fn builtins(facts: &Facts) -> Vec<String> {
    facts
        .imports
        .iter()
        .filter_map(|target| match target {
            Target::Builtin { name, .. } => Some(name.clone()),
            _ => None,
        })
        .collect()
}

/// The symbols of each module, when the reply has a symbols section (`symbols_measured`).
fn symbol_counts(facts: &Facts, modules: &Table<ModuleId, Module>) -> Option<Vec<usize>> {
    let records = facts.sections.iter().find_map(|section| match section {
        Section::Symbols(records) => Some(records),
        _ => None,
    })?;
    let mut by_name: HashMap<&str, usize> = HashMap::new();
    for record in records {
        if let Some(Some(module)) = record.data.fields().module {
            *by_name.entry(module).or_default() += 1;
        }
    }
    Some(
        modules
            .iter()
            .map(|(_, module)| by_name.get(module.name()).copied().unwrap_or(0))
            .collect(),
    )
}

/// The facts of the reply, when the settings of the shell hold for it (AD-372, AD-1116).
fn admitted<'a>(reply: &'a Ingested, settings: &Settings) -> Result<&'a Facts, Reason> {
    let facts = &reply.reply().facts;
    let pinned = archkeel_store::standard_library(&facts.validation.standard_library);
    settings
        .check(facts.profile.as_str(), &pinned)
        .map_err(Reason::Refused)?;
    settings
        .bind_roots(&facts.source.scope)
        .map_err(Reason::Refused)?;
    crate::settings::check_reach(facts).map_err(Reason::Refused)?;
    for file in &facts.files {
        settings
            .admits(file.module.as_str(), file.package.as_str())
            .map_err(Reason::Refused)?;
    }
    Ok(facts)
}
