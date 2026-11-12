// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module and package cycles (slice S3).
//!
//! Reference engine: `check/evaluation/topology.py` `cycle_sections`, `_cycle_records` and
//! `_backed_package_cycles`. A cycle is a component of the condensation with two or more
//! members. An edge never joins a node to itself (slice S2 drops a self edge), so a component of
//! one member is never a cycle. A package cycle names the module cycles that cross two or more
//! of its packages (`backed_by`); a package cycle without one is a roll-up only (AD-98).

use std::collections::{BTreeSet, HashMap};

use archkeel_facts::identity::{stable_id, Part};

use crate::edges::{Edge, Level};
use crate::ids::{ModuleId, PackageId, Table};
use crate::modules::{Module, Package};
use crate::topology::Measured;

/// One cycle: a component of two or more members at one level.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Cycle {
    id: String,
    level: Level,
    members: Vec<String>,
    internal_edges: Vec<String>,
    backed_by: Option<Vec<String>>,
}

impl Cycle {
    /// The id of the cycle record: `stable_id("SCC", level, *members)`.
    pub fn id(&self) -> &str {
        &self.id
    }

    /// The level of the cycle.
    pub fn level(&self) -> Level {
        self.level
    }

    /// The members, in name order.
    pub fn members(&self) -> &[String] {
        &self.members
    }

    /// The ids of the edges between two members, in the order of their (source, target) pairs.
    pub fn internal_edges(&self) -> &[String] {
        &self.internal_edges
    }

    /// For a package cycle, the ids of the module cycles that back it, sorted; `None` for a
    /// module cycle.
    pub fn backed_by(&self) -> Option<&[String]> {
        self.backed_by.as_deref()
    }
}

/// The edges and the measured condensation of one level.
pub(crate) type LevelGraph<'a> = (&'a Measured, &'a [Edge]);

/// The module cycles and the package cycles, sorted by id.
pub(crate) fn cycles(
    modules: &Table<ModuleId, Module>,
    packages: &Table<PackageId, Package>,
    module: LevelGraph<'_>,
    package: LevelGraph<'_>,
) -> Vec<Cycle> {
    let module_names: Vec<&str> = modules.iter().map(|(_, row)| row.name()).collect();
    let package_names: Vec<&str> = packages.iter().map(|(_, row)| row.name()).collect();
    let module_cycles = of_level(Level::Module, &module_names, module);
    let package_of: HashMap<&str, &str> = modules
        .iter()
        .filter_map(|(_, row)| Some((row.name(), packages.get(row.package())?.name())))
        .collect();
    let mut found: Vec<Cycle> = of_level(Level::Package, &package_names, package)
        .into_iter()
        .map(|cycle| backed(cycle, &module_cycles, &package_of))
        .collect();
    found.extend(module_cycles);
    found.sort_by(|a, b| a.id.cmp(&b.id));
    found
}

/// The cycles of one level, in the order of the walk.
fn of_level(level: Level, names: &[&str], (measured, edges): LevelGraph<'_>) -> Vec<Cycle> {
    measured
        .condensation
        .components()
        .iter()
        .filter(|component| component.len() > 1)
        .map(|component| {
            let members: Vec<String> = component
                .iter()
                .filter_map(|&node| measured.nodes.get(node))
                .filter_map(|&row| names.get(row))
                .map(|name| (*name).to_owned())
                .collect();
            let inside: BTreeSet<&str> = members.iter().map(String::as_str).collect();
            let internal_edges = edges
                .iter()
                .filter(|edge| inside.contains(edge.source()) && inside.contains(edge.target()))
                .map(|edge| edge.id().to_owned())
                .collect();
            let mut parts = vec![Part::Text(level.name())];
            parts.extend(members.iter().map(|member| Part::Text(member)));
            Cycle {
                id: stable_id("SCC", &parts),
                level,
                members,
                internal_edges,
                backed_by: None,
            }
        })
        .collect()
}

/// A package cycle with the module cycles that cross two or more of its packages.
fn backed(mut cycle: Cycle, module_cycles: &[Cycle], package_of: &HashMap<&str, &str>) -> Cycle {
    let packages: BTreeSet<&str> = cycle.members.iter().map(String::as_str).collect();
    let mut backed_by: Vec<String> = module_cycles
        .iter()
        .filter(|module_cycle| {
            let crossed: BTreeSet<&str> = module_cycle
                .members
                .iter()
                .filter_map(|member| package_of.get(member.as_str()).copied())
                .filter(|package| packages.contains(package))
                .collect();
            crossed.len() > 1
        })
        .map(|module_cycle| module_cycle.id.clone())
        .collect();
    backed_by.sort();
    cycle.backed_by = Some(backed_by);
    cycle
}

#[cfg(test)]
#[path = "cycles_tests.rs"]
mod tests;
