// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The part of the model that only the reply and the settings give (slices S1 to S3): the
//! modules, packages, imports, edges, measures and cycles. It needs no contract, so a run whose
//! contract the core cannot use yet still has its rows. The core derives it one time per run.

use std::collections::HashMap;

use archkeel_facts::envelope::Facts;
use archkeel_facts::record::FactData;
use archkeel_facts::sections::Section;
use archkeel_store::Ingested;

use crate::coverage::{self, Incomplete};
use crate::cycles::{self, Cycle};
use crate::edges::{self, Edge, Level};
use crate::ids::{Id, ModuleId, PackageId, Table};
use crate::imports::{self, Import, MacroBody};
use crate::modules::{self, Module, Package};
use crate::reason::Reason;
use crate::settings::Settings;
use crate::topology::{self, Measure};

/// The reply part of the model of one run.
#[derive(Debug)]
pub struct Graph {
    modules: Table<ModuleId, Module>,
    packages: Table<PackageId, Package>,
    incomplete: Option<Incomplete>,
    settings: Settings,
    imports: Vec<Import>,
    macro_bodies: Vec<MacroBody>,
    module_edges: Vec<Edge>,
    package_edges: Vec<Edge>,
    module_measures: Vec<Measure>,
    package_measures: Vec<Measure>,
    symbol_counts: Option<Vec<usize>>,
    cycles: Vec<Cycle>,
}

impl Graph {
    /// Derive the reply part of a model from a validated reply and the settings of the shell.
    pub fn derive(reply: &Ingested, settings: Settings) -> Result<Graph, Reason> {
        let facts = admitted(reply, &settings)?;
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
            settings,
            imports: split.imports,
            macro_bodies: split.macro_bodies,
            module_edges,
            package_edges,
            module_measures: module_measured.measures,
            package_measures: package_measured.measures,
            cycles,
        })
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

    /// The settings of the shell: the namespace and the standard library of the profile.
    pub fn settings(&self) -> &Settings {
        &self.settings
    }

    /// The resolved imports that are not macro bodies, in the order of the reply.
    pub fn imports(&self) -> &[Import] {
        &self.imports
    }

    /// The resolved macro bodies, in the order of the reply. Only the fan counts read them.
    pub fn macro_bodies(&self) -> &[MacroBody] {
        &self.macro_bodies
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
    settings
        .check(facts.profile.as_str())
        .map_err(Reason::Refused)?;
    for file in &facts.files {
        settings
            .admits(file.module.as_str(), file.package.as_str())
            .map_err(Reason::Refused)?;
    }
    Ok(facts)
}
