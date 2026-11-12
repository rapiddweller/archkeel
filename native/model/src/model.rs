// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The model of one run: what the contract and the reply give, derived once.

use std::collections::HashMap;
use std::sync::Arc;

use archkeel_contract::{Component, Contract};
use archkeel_store::Ingested;

use crate::domain::Domain;
use crate::graph::Graph;
use crate::ids::{ComponentId, ModuleId, Table};
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

/// The model of one contract of a run: the contract, the reply part (`Graph`), the components,
/// the owner of each module and the state of the scope (made one time, slice S4). The model of
/// an inside contract has the source domain of its mount (AD-385); the models of one tree share
/// the reply part and the scope state.
#[derive(Debug)]
pub struct Model {
    contract: Contract,
    components: Table<ComponentId, Component>,
    owners: HashMap<ModuleId, ComponentId>,
    graph: Arc<Graph>,
    scope: State,
    pairs: Pairs,
    serial: u64,
    domain: Option<Domain>,
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
        // AD-385: the model of an inside contract needs the domain of its mount and the scope
        // state of its tree; only `ModelTree::tree` makes it.
        if contract.mount().is_some() {
            let reason = Reason::Unsupported(Unsupported::InsideRule);
            return Err(Box::new((graph, reason)));
        }
        let components = match Model::components_of(contract) {
            Ok(components) => components,
            Err(reason) => return Err(Box::new((graph, reason))),
        };
        let scope = proof::state(contract, &graph, None);
        Ok(Model::made(
            contract.clone(),
            components,
            Arc::new(graph),
            scope,
            None,
        ))
    }

    /// The model of one contract over a shared reply part, with its scope state and domain.
    pub(crate) fn made(
        contract: Contract,
        components: Table<ComponentId, Component>,
        graph: Arc<Graph>,
        scope: State,
        domain: Option<Domain>,
    ) -> Model {
        let modules = graph.modules();
        let owners = match &domain {
            Some(domain) => {
                let held = domain.held().iter();
                let rows = held.filter_map(|id| modules.get(*id).map(|row| (*id, row)));
                ownership::owners(&components, rows)
            }
            None => ownership::owners(&components, modules.iter()),
        };
        // Slice S7 (AD-384). In a tree each gap is already a cause of the shared state (AD-385).
        let pairs = pair_gaps::pairs(&contract, &components, &graph);
        Model {
            contract,
            components,
            owners,
            graph,
            scope,
            pairs,
            serial: SERIALS.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
            domain,
        }
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
        self.owners.get(&module).copied()
    }

    /// The modules of the domain that a rule `source` selects (`_modules_for_rule_source` over
    /// the observed modules of the scope).
    pub fn source_modules(&self, source: &str) -> Vec<ModuleId> {
        let mut found = ownership::source_modules(&self.components, self.graph.modules(), source);
        found.retain(|module| self.holds(*module));
        found
    }

    /// True when the module lies in the source domain of this model: always for a root, and for
    /// the model of an inside contract when its mount owns the module (`source_modules`).
    pub fn holds(&self, module: ModuleId) -> bool {
        self.domain
            .as_ref()
            .is_none_or(|domain| domain.holds(module))
    }

    /// True when the module of this name lies in the source domain of this model.
    pub fn selects(&self, module: &str) -> bool {
        self.domain
            .as_ref()
            .is_none_or(|domain| domain.selects(module))
    }

    /// True when a package of the reply lies below a package of the parent of this mount
    /// (`source_roots`); always for a root.
    pub fn below_roots(&self, package: &str) -> bool {
        self.domain
            .as_ref()
            .is_none_or(|domain| domain.below_roots(package))
    }

    /// True for the model of an inside contract.
    pub fn is_mount(&self) -> bool {
        self.domain.is_some()
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
