// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The component cycles of a model (slice S7, AD-374 point 7, AD-384).
//!
//! Reference engine: `check/evaluation/rules.py` `_component_cycle_violations` with
//! `ir/graph.py` `strongly_connected_components`. The nodes are the components of the contract;
//! an import whose two ends have one owner each, and two different owners, is an edge between
//! them. A component of the condensation with two or more members is a cycle. The walk is the
//! explicit stack of `condensation.rs`, so no depth reaches the call stack.

use std::collections::BTreeSet;

use crate::condensation::condense;
use crate::ids::{ComponentId, Id};
use crate::imports::Import;
use crate::model::Model;

/// One component cycle: its member labels, sorted, and the imports between two members.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ComponentCycle {
    members: Vec<String>,
    imports: Vec<usize>,
}

impl ComponentCycle {
    /// The labels of the members, sorted.
    pub fn members(&self) -> &[String] {
        &self.members
    }

    /// The imports between two members, in the order of the reply.
    pub fn imports<'m>(&self, model: &'m Model) -> Vec<&'m Import> {
        let all = model.graph().imports();
        self.imports
            .iter()
            .filter_map(|&index| all.get(index))
            .collect()
    }
}

/// The component cycles of a model, in the order of their first member label. It is a free
/// function, not a method: the collector cannot place a method of an `impl` block of another
/// file, so a call of it from another crate would be a pair gap of the self-check (AD-357).
pub fn cycles_of_components(model: &Model) -> Vec<ComponentCycle> {
    let owner = |module: &str| crate::ownership::owner_of(model.components(), module);
    let owned: Vec<Option<(ComponentId, ComponentId)>> = model
        .graph()
        .imports()
        .iter()
        .map(|import| {
            let pair = (
                owner(import.source_module())?,
                owner(import.target_module())?,
            );
            (pair.0 != pair.1).then_some(pair)
        })
        .collect();
    let edges: BTreeSet<(usize, usize)> = owned
        .iter()
        .flatten()
        .map(|(source, target)| (source.index(), target.index()))
        .collect();
    let edges: Vec<(usize, usize)> = edges.into_iter().collect();
    let condensation = condense(model.components().len(), &edges);
    let label = |index: usize| {
        model
            .components()
            .iter()
            .find(|(id, _)| id.index() == index)
            .map(|(_, component)| component.label().as_text().to_owned())
    };
    let mut found: Vec<ComponentCycle> = condensation
        .components()
        .iter()
        .filter(|component| component.len() > 1)
        .map(|component| {
            let inside: BTreeSet<usize> = component.iter().copied().collect();
            let mut members: Vec<String> = component.iter().filter_map(|&i| label(i)).collect();
            members.sort();
            let imports = owned
                .iter()
                .enumerate()
                .filter_map(|(index, pair)| {
                    let (source, target) = (*pair)?;
                    let both = inside.contains(&source.index()) && inside.contains(&target.index());
                    both.then_some(index)
                })
                .collect();
            ComponentCycle { members, imports }
        })
        .collect();
    found.sort_by(|a, b| a.members.cmp(&b.members));
    found
}

#[cfg(test)]
#[path = "component_cycles_tests.rs"]
mod tests;
