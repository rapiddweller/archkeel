// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The fan-in, fan-out and condensation rank of each module and package (slice S3).
//!
//! Reference engine: `check/evaluation/topology.py` `module_records` and `package_records`, and
//! `check/evaluation/imports.py` `count_macro_bodies`. The rank of a module or a package comes
//! from the condensation of the nodes of its table and the edges of its level: an edge to a node
//! outside the table changes no rank. A macro body adds to the fan counts of two modules only
//! when no edge has its pair; it never changes a rank or a cycle.

use std::collections::{BTreeSet, HashMap};

use crate::{
    condensation::{condense, Condensation},
    edges::Edge,
    ids::{Id, ModuleId, PackageId, Table},
    imports::MacroBody,
    modules::{Module, Package},
};

/// The fan-in, fan-out and rank of one module or package.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Measure {
    fan_in: usize,
    fan_out: usize,
    rank: usize,
}

impl Measure {
    /// The number of edges (and macro body pairs, for a module) that end at the node.
    pub fn fan_in(&self) -> usize {
        self.fan_in
    }

    /// The number of edges (and macro body pairs, for a module) that start at the node.
    pub fn fan_out(&self) -> usize {
        self.fan_out
    }

    /// The condensation rank of the node.
    pub fn rank(&self) -> usize {
        self.rank
    }
}

/// The measures of the nodes of one level and the condensation that gave their ranks. The
/// condensation also gives the cycles of that level.
#[derive(Debug)]
pub(crate) struct Measured {
    pub(crate) measures: Vec<Measure>,
    pub(crate) condensation: Condensation,
    /// The node index (into the table) of each name, in name order.
    pub(crate) nodes: Vec<usize>,
}

/// The measures of the modules: the module edges and the macro bodies.
pub(crate) fn modules(
    table: &Table<ModuleId, Module>,
    edges: &[Edge],
    macro_bodies: &[MacroBody],
) -> Measured {
    let names: Vec<&str> = table.iter().map(|(_, module)| module.name()).collect();
    let mut measured = measure(&names, edges);
    let known: BTreeSet<(&str, &str)> = edges
        .iter()
        .map(|edge| (edge.source(), edge.target()))
        .collect();
    let pairs: BTreeSet<(&str, &str)> = macro_bodies
        .iter()
        .map(|body| (body.source_module(), body.target_module()))
        .filter(|pair| !known.contains(pair))
        .collect();
    let at = last_index(&names);
    for (source, target) in pairs {
        if let (Some(&from), Some(&to)) = (at.get(source), at.get(target)) {
            if source != target {
                bump(&mut measured.measures, from, |measure| measure.fan_out += 1);
                bump(&mut measured.measures, to, |measure| measure.fan_in += 1);
            }
        }
    }
    measured
}

/// The measures of the packages: the package edges.
pub(crate) fn packages(table: &Table<PackageId, Package>, edges: &[Edge]) -> Measured {
    let names: Vec<&str> = table.iter().map(|(_, package)| package.name()).collect();
    measure(&names, edges)
}

/// The fan counts of each row and the ranks of the condensation over the distinct names. A row
/// whose name repeats gets the measure of that name, as a `Counter` and a rank by name give it.
fn measure(names: &[&str], edges: &[Edge]) -> Measured {
    let distinct: Vec<&str> = names
        .iter()
        .copied()
        .collect::<BTreeSet<&str>>()
        .into_iter()
        .collect();
    let index: HashMap<&str, usize> = distinct
        .iter()
        .enumerate()
        .map(|(at, n)| (*n, at))
        .collect();
    let mut fan_in: HashMap<&str, usize> = HashMap::new();
    let mut fan_out: HashMap<&str, usize> = HashMap::new();
    for edge in edges {
        *fan_out.entry(edge.source()).or_default() += 1;
        *fan_in.entry(edge.target()).or_default() += 1;
    }
    let pairs: Vec<(usize, usize)> = edges
        .iter()
        .filter_map(|edge| Some((*index.get(edge.source())?, *index.get(edge.target())?)))
        .collect();
    let condensation = condense(distinct.len(), &pairs);
    let measures = names
        .iter()
        .map(|name| Measure {
            fan_in: fan_in.get(name).copied().unwrap_or(0),
            fan_out: fan_out.get(name).copied().unwrap_or(0),
            rank: index.get(name).map_or(0, |&at| condensation.rank(at)),
        })
        .collect();
    let first = first_index(names);
    let nodes = distinct
        .iter()
        .map(|name| first.get(name).copied().unwrap_or(0))
        .collect();
    Measured {
        measures,
        condensation,
        nodes,
    }
}

/// Add to the measure of one row.
fn bump(measures: &mut [Measure], row: usize, change: impl Fn(&mut Measure)) {
    if let Some(measure) = measures.get_mut(row) {
        change(measure);
    }
}

fn first_index<'a>(names: &[&'a str]) -> HashMap<&'a str, usize> {
    let mut found = HashMap::new();
    for (at, name) in names.iter().enumerate() {
        found.entry(*name).or_insert(at);
    }
    found
}

/// The last row of each name: `count_macro_bodies` keys its rows by name, so the last wins.
fn last_index<'a>(names: &[&'a str]) -> HashMap<&'a str, usize> {
    names.iter().enumerate().map(|(at, n)| (*n, at)).collect()
}

/// The measure of a row of a table.
pub(crate) fn of<I: Id>(measures: &[Measure], id: I) -> Measure {
    measures.get(id.index()).copied().unwrap_or_default()
}

#[cfg(test)]
#[path = "topology_tests.rs"]
pub(crate) mod tests;
