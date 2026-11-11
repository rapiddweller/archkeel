// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The model of one run: what the contract and the reply give, derived once.

use archkeel_contract::{Component, Contract};
use archkeel_store::Ingested;

use crate::coverage::Incomplete;
use crate::edges::{Edge, Level};
use crate::graph::Graph;
use crate::ids::{ComponentId, Id, ModuleId, PackageId, Table};
use crate::imports::Import;
use crate::modules::{Module, Package};
use crate::ownership;
use crate::reason::{Reason, Unsupported};
use crate::section::Section;
use crate::settings::Settings;

/// The rows of one derived section that the model holds. The rows of the sections of slice S3
/// come from the `Graph`; each other section has no rows yet, and a section that is not ported
/// has no empty form.
#[derive(Debug)]
pub enum Rows {}

/// The model of one run: the reply part (`Graph`), the components and the owner of each module.
#[derive(Debug)]
pub struct Model {
    components: Table<ComponentId, Component>,
    owners: Vec<Option<ComponentId>>,
    graph: Graph,
}

impl Model {
    /// Derive the model of a contract, a validated reply and the settings of the shell.
    pub fn derive(
        contract: &Contract,
        reply: &Ingested,
        settings: Settings,
    ) -> Result<Model, Reason> {
        let graph = Graph::derive(reply, settings)?;
        Ok(Model::of(Model::components_of(contract)?, graph))
    }

    /// The components of a contract, in contract order: the first input of `Model::of`.
    pub fn components_of(contract: &Contract) -> Result<Table<ComponentId, Component>, Reason> {
        Table::of_rows(contract.components().to_vec()).ok_or(Reason::TooManyRows("components"))
    }

    /// The model of the components of a contract and the reply part of the run. The reply part
    /// moves into the model, so a run derives it one time.
    pub fn of(components: Table<ComponentId, Component>, graph: Graph) -> Model {
        let owners = ownership::owners(&components, graph.modules());
        Model {
            components,
            owners,
            graph,
        }
    }

    /// The reply part of the model.
    pub fn graph(&self) -> &Graph {
        &self.graph
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
        self.graph.modules()
    }

    /// The packages of the reply, in name order.
    pub fn packages(&self) -> &Table<PackageId, Package> {
        self.graph.packages()
    }

    /// The one component that owns a module, or `None` when zero or many claim it.
    pub fn owner(&self, module: ModuleId) -> Option<ComponentId> {
        self.owners.get(module.index()).copied().flatten()
    }

    /// The modules that a rule `source` selects (`_modules_for_rule_source`).
    pub fn source_modules(&self, source: &str) -> Vec<ModuleId> {
        ownership::source_modules(&self.components, self.graph.modules(), source)
    }

    /// What the reply proves not seen, if anything. It can only give UNKNOWN, never PASS.
    pub fn incomplete(&self) -> Option<Incomplete> {
        self.graph.incomplete()
    }

    /// The settings of the shell: the namespace and the standard library of the profile.
    pub fn settings(&self) -> &Settings {
        self.graph.settings()
    }

    /// The resolved imports that are not macro bodies, in the order of the reply.
    pub fn imports(&self) -> &[Import] {
        self.graph.imports()
    }

    /// The edges of one level, in the order of their (source, target) pairs.
    pub fn edges(&self, level: Level) -> &[Edge] {
        self.graph.edges(level)
    }

    /// The rows of one section that the model holds. None is ported here: the rows of slice S3
    /// come from the `Graph`, and each other section answers its slice by name.
    pub fn rows(&self, section: Section) -> Result<Rows, Reason> {
        Err(Reason::Unsupported(Unsupported::Section(section)))
    }
}

#[cfg(test)]
#[path = "model_tests.rs"]
mod tests;
