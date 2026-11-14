// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The part of the model that only the reply and the settings give (slices S1 to S3): the
//! modules, packages, imports, edges, measures and cycles. It needs no contract, so a run whose
//! contract the core cannot use yet still has its rows. The core derives it one time per run.
//! The macro bodies are typed rows of the split (`MacroBody`): the fan counts of the modules
//! read them while the graph is derived, and nothing reads them after.

use std::collections::HashMap;

use archkeel_facts::envelope::{Facts, Target};
use archkeel_facts::record::FactData;
use archkeel_facts::sections::Section;
use archkeel_store::Ingested;

use crate::constructs::Constructs;
use crate::coverage::{self, Incomplete};
use crate::cycles::{self, Cycle};
use crate::edges::{self, Edge, Level};
use crate::ids::{Id, ModuleId, PackageId, Table};
use crate::imports::{self, Import};
use crate::modules::{self, Module, Package};
use crate::needs::Needs;
use crate::observed::{self, Observed};
use crate::reason::Reason;
use crate::settings::Settings;
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
    module_edges: Vec<Edge>,
    package_edges: Vec<Edge>,
    module_measures: Vec<Measure>,
    package_measures: Vec<Measure>,
    symbol_counts: Option<Vec<usize>>,
    cycles: Vec<Cycle>,
    observed: Observed,
    builtins: Vec<String>,
    constructs: Constructs,
    /// The symbol table, when a need of the run reads it (AD-498).
    symbols: Option<crate::symbols::Symbols>,
}

impl Graph {
    /// Derive the reply part of a model from a validated reply and the settings of the shell.
    pub fn derive(reply: &Ingested, settings: Settings) -> Result<Graph, Reason> {
        Self::derive_for(reply, settings, &Needs::default())
    }

    /// Derive the reply part for a run with `needs`: a need that reads the symbols adds the
    /// symbol table (AD-498). Without one, the reply part is the same as `derive` gives.
    pub fn derive_for(
        reply: &Ingested,
        settings: Settings,
        needs: &Needs,
    ) -> Result<Graph, Reason> {
        let facts = admitted(reply, &settings)?;
        let mut graph = Self::from_facts(facts, settings)?;
        if needs.symbols() {
            graph.symbols = Some(crate::symbols::Symbols::derive(facts, &graph.modules));
        }
        Ok(graph)
    }

    fn from_facts(facts: &Facts, settings: Settings) -> Result<Graph, Reason> {
        let settings = settings.bound(&facts.adapter.name, facts.profile.as_str());
        let (modules, packages) = modules::tables(&facts.files)?;
        let split = imports::split(facts);
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
        Ok(Graph {
            symbol_counts: symbol_counts(facts, &modules),
            modules,
            packages,
            incomplete: coverage::incomplete(&facts.coverage, split.unknown),
            gaps: crate::gaps::coverage_gaps(&facts.coverage),
            settings,
            imports: split.imports,
            module_edges,
            package_edges,
            module_measures: module_measured.measures,
            package_measures: package_measured.measures,
            cycles,
            observed: observed::observed(facts),
            builtins: builtins(facts),
            constructs: Constructs::derive(facts)?,
            symbols: None,
        })
    }

    /// Recorded inputs for unit tests only; no production caller can bypass the store.
    #[cfg(test)]
    pub(crate) fn recorded(facts: &Facts, settings: Settings) -> Result<Graph, Reason> {
        Self::from_facts(facts, settings)
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

    /// The symbol table, when a need of the run reads it (AD-498).
    pub(crate) fn symbols(&self) -> Option<&crate::symbols::Symbols> {
        self.symbols.as_ref()
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

/// The facts of the reply, when the settings of the shell hold for it (AD-372): the profile is
/// the profile of the reply, and each module lies in the namespace.
fn admitted<'a>(reply: &'a Ingested, settings: &Settings) -> Result<&'a Facts, Reason> {
    let facts = &reply.reply().facts;
    let pinned = archkeel_store::standard_library(facts.profile);
    settings
        .check(facts.profile.as_str(), &pinned)
        .map_err(Reason::Refused)?;
    settings
        .bind_roots(&facts.source.scope)
        .map_err(Reason::Refused)?;
    for file in &facts.files {
        settings
            .admits(file.module.as_str(), file.package.as_str())
            .map_err(Reason::Refused)?;
    }
    Ok(facts)
}
