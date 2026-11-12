// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module and package edges of the resolved imports (slice S2).
//!
//! Reference engine: `check/evaluation/topology.py` `aggregate_edges`. A module edge needs a
//! target that is a module of the reply; a package edge needs a target package in the scope of
//! the namespace. Neither keeps a self edge. The edges are in the order of their (source, target)
//! pairs. The ranks of an edge come from the condensation of the edges of its level (slice S3):
//! the nodes are the ends of the edges, as `aggregate_edges` ranks them.
//!
//! An edge holds one source and one target. A later record of transitive paths (one record per
//! package with its targets) is a different type, so this type does not need to change for it.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::fmt;

use archkeel_facts::envelope::FileFact;
use archkeel_facts::identity::{stable_id, Part};

use crate::condensation::condense;
use crate::imports::Import;
use crate::ownership::in_scope;

/// The level of an edge.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Level {
    /// Between two modules.
    Module,
    /// Between two packages.
    Package,
}

impl Level {
    /// The word of the level in the rows (`module`, `package`).
    pub fn name(self) -> &'static str {
        match self {
            Level::Module => "module",
            Level::Package => "package",
        }
    }
}

impl fmt::Display for Level {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.name())
    }
}

/// One edge: the imports from `source` to `target` at one level.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Edge {
    id: String,
    level: Level,
    source: String,
    target: String,
    imports: Vec<String>,
    type_checking: usize,
    bidirectional: bool,
    source_rank: usize,
    target_rank: usize,
}

impl Edge {
    /// The level of the edge.
    pub fn level(&self) -> Level {
        self.level
    }

    /// The id of the edge record: `stable_id("EDGE", level, source, target)`.
    pub fn id(&self) -> &str {
        &self.id
    }

    /// The source module or package.
    pub fn source(&self) -> &str {
        &self.source
    }

    /// The target module or package.
    pub fn target(&self) -> &str {
        &self.target
    }

    /// The ids of the imports of the edge, sorted.
    pub fn imports(&self) -> &[String] {
        &self.imports
    }

    /// The number of imports that the program reads when it runs.
    pub fn runtime(&self) -> usize {
        self.imports.len().saturating_sub(self.type_checking)
    }

    /// The number of imports that only a type check reads.
    pub fn type_checking(&self) -> usize {
        self.type_checking
    }

    /// True when the reverse edge exists at the same level.
    pub fn bidirectional(&self) -> bool {
        self.bidirectional
    }

    /// The condensation rank of the source in the graph of the edges of this level.
    pub fn source_rank(&self) -> usize {
        self.source_rank
    }

    /// The condensation rank of the target in the graph of the edges of this level.
    pub fn target_rank(&self) -> usize {
        self.target_rank
    }
}

/// The module edges and the package edges of the files and resolved imports of a reply.
pub(crate) fn both(
    files: &[FileFact],
    imports: &[Import],
    namespace: &str,
) -> (Vec<Edge>, Vec<Edge>) {
    let names: HashSet<&str> = files.iter().map(|file| file.module.as_str()).collect();
    (
        edges(imports, Level::Module, &names, namespace),
        edges(imports, Level::Package, &names, namespace),
    )
}

/// The edges of one level, in the order of their (source, target) pairs, with their ranks.
fn edges(imports: &[Import], level: Level, modules: &HashSet<&str>, namespace: &str) -> Vec<Edge> {
    let mut buckets: BTreeMap<(&str, &str), (Vec<&str>, usize)> = BTreeMap::new();
    for import in imports {
        let (source, target) = match level {
            Level::Module => (import.source_module(), import.target_module()),
            Level::Package => (import.source_package(), import.target_package()),
        };
        let inside = match level {
            Level::Module => modules.contains(target),
            Level::Package => in_scope(target, namespace),
        };
        if !inside || source == target {
            continue;
        }
        let bucket = buckets.entry((source, target)).or_default();
        bucket.0.push(import.id());
        bucket.1 += usize::from(import.under_type_checking());
    }
    let mut edges: Vec<Edge> = buckets
        .iter()
        .map(|(&(source, target), (ids, type_checking))| {
            let mut ids: Vec<String> = ids.iter().map(|id| (*id).to_owned()).collect();
            ids.sort();
            Edge {
                id: stable_id(
                    "EDGE",
                    &[
                        Part::Text(level.name()),
                        Part::Text(source),
                        Part::Text(target),
                    ],
                ),
                level,
                source: source.to_owned(),
                target: target.to_owned(),
                imports: ids,
                type_checking: *type_checking,
                bidirectional: buckets.contains_key(&(target, source)),
                source_rank: 0,
                target_rank: 0,
            }
        })
        .collect();
    rank(&mut edges);
    edges
}

/// Set the ranks of the edges of one level: the condensation of the graph whose nodes are the
/// ends of the edges (`condensation_ranks` in `aggregate_edges`).
fn rank(edges: &mut [Edge]) {
    let names: BTreeSet<&str> = edges
        .iter()
        .flat_map(|edge| [edge.source.as_str(), edge.target.as_str()])
        .collect();
    let index: HashMap<&str, usize> = names.iter().enumerate().map(|(at, n)| (*n, at)).collect();
    let at = |name: &str| index.get(name).copied().unwrap_or(usize::MAX);
    let pairs: Vec<(usize, usize)> = edges
        .iter()
        .map(|edge| (at(&edge.source), at(&edge.target)))
        .collect();
    let condensation = condense(names.len(), &pairs);
    for (edge, (source, target)) in edges.iter_mut().zip(pairs) {
        edge.source_rank = condensation.rank(source);
        edge.target_rank = condensation.rank(target);
    }
}

#[cfg(test)]
#[path = "edges_tests.rs"]
mod tests;
