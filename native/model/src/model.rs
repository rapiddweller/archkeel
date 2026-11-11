// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The model of one run: what the contract and the reply give, derived once.

use archkeel_contract::{Component, Contract};
use archkeel_store::Ingested;

use crate::coverage::{self, Incomplete};
use crate::ids::{ComponentId, Id, ModuleId, PackageId, Table};
use crate::modules::{self, Module, Package};
use crate::ownership;
use crate::reason::{Reason, Unsupported};
use crate::section::Section;

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
}

impl Model {
    /// Derive the model of a contract and a validated reply.
    pub fn derive(contract: &Contract, reply: &Ingested) -> Result<Model, Reason> {
        let components = Table::of_rows(contract.components().to_vec())
            .ok_or(Reason::TooManyRows("components"))?;
        let facts = &reply.reply().facts;
        let (modules, packages) = modules::tables(&facts.files)?;
        let owners = ownership::owners(&components, &modules);
        Ok(Model {
            components,
            modules,
            packages,
            owners,
            incomplete: coverage::incomplete(&facts.coverage),
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

    /// The number of source files of the reply.
    pub fn files(&self) -> usize {
        self.modules.len()
    }

    /// The rows of one section. No section is ported yet: each answers its slice by name.
    pub fn rows(&self, section: Section) -> Result<Rows, Reason> {
        Err(Reason::Unsupported(Unsupported::Section(section)))
    }
}

#[cfg(test)]
#[path = "model_tests.rs"]
mod tests;
