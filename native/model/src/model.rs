// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The model of one run: what the contract and the reply give, derived once.

use archkeel_contract::{Component, Contract};
use archkeel_store::Ingested;

use crate::graph::Graph;
use crate::ids::{ComponentId, Id, ModuleId, Table};
use crate::ownership;
use crate::pair_gaps::{self, Pairs};
use crate::proof::{self, State};
use crate::reason::{Reason, Unsupported};
use crate::section::Section;
use crate::settings::Settings;

/// The rows of one derived section that the model holds. The rows of the sections of slice S3
/// come from the `Graph`; each other section has no rows yet, and a section that is not ported
/// has no empty form.
#[derive(Debug)]
pub enum Rows {}

/// The model of one run: the contract, the reply part (`Graph`), the components, the owner of
/// each module and the state of the scope (made one time, slice S4).
#[derive(Debug)]
pub struct Model {
    contract: Contract,
    components: Table<ComponentId, Component>,
    owners: Vec<Option<ComponentId>>,
    graph: Graph,
    scope: State,
    pairs: Pairs,
    serial: u64,
}

/// The serial of the next model: a PASS decision names the model that made it (AD-378).
static SERIALS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);

impl Model {
    /// Derive the model of a contract, a validated reply and the settings of the shell.
    pub fn derive(
        contract: &Contract,
        reply: &Ingested,
        settings: Settings,
    ) -> Result<Model, Reason> {
        let graph = Graph::derive(reply, settings)?;
        Model::of(contract, graph).map_err(|refused| refused.1)
    }

    /// The components of a contract, in contract order: the first input of `Model::of`.
    pub fn components_of(contract: &Contract) -> Result<Table<ComponentId, Component>, Reason> {
        Table::of_rows(contract.components().to_vec()).ok_or(Reason::TooManyRows("components"))
    }

    /// The model of a contract and the reply part of the run. The reply part moves into the
    /// model, so a run derives it one time; a contract with too many components gives it back.
    pub fn of(contract: &Contract, graph: Graph) -> Result<Model, Box<(Graph, Reason)>> {
        let components = match Model::components_of(contract) {
            Ok(components) => components,
            Err(reason) => return Err(Box::new((graph, reason))),
        };
        let owners = ownership::owners(&components, graph.modules());
        let trusted = graph.settings().producer() == crate::settings::Producer::Trusted;
        let scope = proof::state(contract, &graph, trusted);
        let pairs = pair_gaps::pairs(contract, &components, &graph);
        Ok(Model {
            contract: contract.clone(),
            components,
            owners,
            graph,
            scope,
            pairs,
            serial: SERIALS.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
        })
    }

    /// The serial of this model, distinct for each model of the process.
    pub(crate) fn serial(&self) -> u64 {
        self.serial
    }

    /// The contract of the model.
    pub fn contract(&self) -> &Contract {
        &self.contract
    }

    /// The state of the scope of the model (`Scope::complete` reads it).
    pub(crate) fn scope_state(&self) -> &State {
        &self.scope
    }

    /// The pair gaps of the run, classified by the drop rule (slice S7, AD-384).
    pub(crate) fn pairs(&self) -> &Pairs {
        &self.pairs
    }

    /// The number of pair gaps that the drop rule keeps. The reference engine makes each rule
    /// UNKNOWN for one; the core holds only the rules that a gap can change (AD-384).
    pub fn kept_pair_gaps(&self) -> usize {
        self.pairs.kept.len()
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

    /// The one component that owns a module, or `None` when zero or many claim it.
    pub fn owner(&self, module: ModuleId) -> Option<ComponentId> {
        self.owners.get(module.index()).copied().flatten()
    }

    /// The modules that a rule `source` selects (`_modules_for_rule_source`).
    pub fn source_modules(&self, source: &str) -> Vec<ModuleId> {
        ownership::source_modules(&self.components, self.graph.modules(), source)
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
