// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The model of one run: what the contract and the reply give, derived once.

use archkeel_contract::{Component, Contract};
use archkeel_facts::envelope::Facts;
use archkeel_store::Ingested;

use crate::coverage::{self, Incomplete};
use crate::edges::{self, Edge, Level};
use crate::ids::{ComponentId, Id, ModuleId, PackageId, Table};
use crate::imports::{self, Import};
use crate::modules::{self, Module, Package};
use crate::ownership;
use crate::reason::{Reason, Unsupported};
use crate::section::Section;
use crate::settings::Settings;

/// The rows of one derived section. It has one variant per ported section. The rows of
/// `modules` and `packages` need the edges of S2 and the ranks of S3, so no section is ported
/// yet: a section that is not ported has no empty form.
#[derive(Debug)]
pub enum Rows {}

/// The model of one run.
#[derive(Debug)]
pub struct Model {
    components: Table<ComponentId, Component>,
    modules: Table<ModuleId, Module>,
    packages: Table<PackageId, Package>,
    owners: Vec<Option<ComponentId>>,
    incomplete: Option<Incomplete>,
    settings: Settings,
    imports: Vec<Import>,
    module_edges: Vec<Edge>,
    package_edges: Vec<Edge>,
}

impl Model {
    /// Derive the model of a contract, a validated reply and the settings of the shell.
    pub fn derive(
        contract: &Contract,
        reply: &Ingested,
        settings: Settings,
    ) -> Result<Model, Reason> {
        let components = Table::of_rows(contract.components().to_vec())
            .ok_or(Reason::TooManyRows("components"))?;
        let facts = admitted(reply, &settings)?;
        let (modules, packages) = modules::tables(&facts.files)?;
        let owners = ownership::owners(&components, &modules);
        let (imports, unknown_imports) = imports::split(facts);
        let (module_edges, package_edges) =
            edges::both(&facts.files, &imports, settings.namespace());
        Ok(Model {
            components,
            modules,
            packages,
            owners,
            incomplete: coverage::incomplete(&facts.coverage, unknown_imports),
            settings,
            imports,
            module_edges,
            package_edges,
        })
    }

    /// The components of the contract, in contract order.
    pub fn components(&self) -> &Table<ComponentId, Component> {
        &self.components
    }

    /// The component of a label.
    pub fn component(&self, label: &str) -> Option<ComponentId> {
        self.components
            .iter()
            .find(|(_, component)| component.label().as_text() == label)
            .map(|(id, _)| id)
    }

    /// The modules of the reply, in the order of the reply.
    pub fn modules(&self) -> &Table<ModuleId, Module> {
        &self.modules
    }

    /// The packages of the reply, in name order.
    pub fn packages(&self) -> &Table<PackageId, Package> {
        &self.packages
    }

    /// The one component that owns a module, or `None` when zero or many claim it.
    pub fn owner(&self, module: ModuleId) -> Option<ComponentId> {
        self.owners.get(module.index()).copied().flatten()
    }

    /// The modules that a rule `source` selects (`_modules_for_rule_source`).
    pub fn source_modules(&self, source: &str) -> Vec<ModuleId> {
        ownership::source_modules(&self.components, &self.modules, source)
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

    /// The edges of one level, in the order of their (source, target) pairs.
    pub fn edges(&self, level: Level) -> &[Edge] {
        match level {
            Level::Module => &self.module_edges,
            Level::Package => &self.package_edges,
        }
    }

    /// The rows of one section. No section is ported yet: each answers its slice by name.
    pub fn rows(&self, section: Section) -> Result<Rows, Reason> {
        Err(Reason::Unsupported(Unsupported::Section(section)))
    }
}

/// The package and module edges of a reply. They need no contract, so a run whose contract the
/// core cannot use yet still has them.
pub fn reply_edges(reply: &Ingested, settings: &Settings) -> Result<Vec<Edge>, Reason> {
    let facts = admitted(reply, settings)?;
    let (imports, _) = imports::split(facts);
    let (module, package) = edges::both(&facts.files, &imports, settings.namespace());
    Ok(package.into_iter().chain(module).collect())
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

#[cfg(test)]
#[path = "model_tests.rs"]
mod tests;
