// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The levels of the Explorer (AD-606): for the system and for each component, its children, the
//! observed imports between them, the declared requirements between them and the difference of the
//! two lists. An import counts for the two children that hold its modules; a requirement counts for
//! the two children that hold its components.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{json, Value};

use super::atlas_tree::{held, Finding, Refs, Tree};
use super::frame::{Frame, Topology};

/// One import between two modules of the topology.
struct Cell {
    source: usize,
    target: usize,
    owners: (Option<usize>, Option<usize>),
    count: usize,
    status: &'static str,
    findings: Vec<usize>,
}

/// The rows of the payload that the levels make, and the requirements of each node.
pub(super) struct Levels {
    pub(super) modules: Vec<Value>,
    pub(super) assignments: Vec<Value>,
    pub(super) cells: Vec<Value>,
    pub(super) rows: Vec<Value>,
    pub(super) deviations: Vec<Value>,
    pub(super) balance: Value,
    requires: BTreeMap<usize, Vec<(usize, usize)>>,
    used_by: BTreeMap<usize, Vec<(usize, usize)>>,
}

impl Levels {
    /// The declared targets of a node at its level, with the observed imports of each.
    pub(super) fn requires(&self, node: usize) -> &[(usize, usize)] {
        self.requires.get(&node).map_or(&[], Vec::as_slice)
    }

    /// The nodes that import a node at its level, with the import sites of each.
    pub(super) fn used_by(&self, node: usize) -> Vec<[usize; 2]> {
        self.used_by
            .get(&node)
            .map(|rows| rows.iter().map(|(n, c)| [*n, *c]).collect())
            .unwrap_or_default()
    }
}

/// The worse of two statuses: FAIL before UNKNOWN before PASS.
fn worse(a: &'static str, b: &'static str) -> &'static str {
    let rank = |s: &str| ["PASS", "UNKNOWN", "FAIL"].iter().position(|x| *x == s);
    if rank(b) > rank(a) {
        b
    } else {
        a
    }
}

fn cells(frame: &Frame, topology: &Topology, tree: &Tree, found: &[Finding]) -> Vec<Cell> {
    let index: BTreeMap<&str, usize> = topology
        .modules
        .iter()
        .enumerate()
        .map(|(i, m)| (m.name.as_str(), i))
        .collect();
    let held = held(frame);
    let failing = |rules: &[String]| {
        rules
            .iter()
            .any(|r| frame.rules.get(r).is_some_and(|row| row.1 == "FAIL"))
    };
    topology
        .edges
        .iter()
        .filter(|e| e.resolution == "resolved")
        .filter_map(|e| {
            let (source, target) = (
                *index.get(e.source.as_str())?,
                *index.get(e.target.as_str())?,
            );
            let pair = (e.source.clone(), e.target.clone());
            let status = if failing(&e.rules) {
                "FAIL"
            } else if held.contains(&pair) {
                "UNKNOWN"
            } else {
                "PASS"
            };
            Some(Cell {
                source,
                target,
                owners: (
                    tree.owner.get(&e.source).copied(),
                    tree.owner.get(&e.target).copied(),
                ),
                count: e.count,
                status,
                findings: (0..found.len())
                    .filter(|f| found[*f].pair.as_ref() == Some(&pair))
                    .collect(),
            })
        })
        .collect()
}

fn modules(
    topology: &Topology,
    tree: &Tree,
    cells: &[Cell],
    refs: &mut Refs,
) -> (Vec<Value>, Vec<Value>) {
    let mut fan: Vec<(BTreeSet<usize>, BTreeSet<usize>)> =
        vec![Default::default(); topology.modules.len()];
    for cell in cells {
        fan[cell.source].1.insert(cell.target);
        fan[cell.target].0.insert(cell.source);
    }
    let owned = refs.id("A component of the contract owns the module.");
    let unowned = refs.id("No component of the contract owns the module.");
    let mut rows = Vec::new();
    let mut assignments = Vec::new();
    for (i, module) in topology.modules.iter().enumerate() {
        rows.push(json!({
            "id": module.name, "name": module.name, "path": module.path, "rank": null,
            "fan_in": fan[i].0.len(), "fan_out": fan[i].1.len(), "evidence_ids": [],
            "symbol_coverage": 0, "symbols": null,
        }));
        let owner = tree
            .owner
            .get(&module.name)
            .map(|n| refs.id(&tree.nodes[*n].id));
        let candidates: Vec<usize> = owner.into_iter().collect();
        let (status, reason) = if owner.is_some() {
            ("PASS", owned)
        } else {
            ("UNKNOWN", unowned)
        };
        assignments.push(json!([i, owner, candidates, status, reason]));
    }
    (rows, assignments)
}

type Pairs = BTreeMap<(usize, usize), (usize, &'static str)>;

/// The observed and the declared pairs between the children of one level.
fn pairs(
    level: Option<usize>,
    tree: &Tree,
    cells: &[Cell],
    declared: &[(usize, usize, usize)],
) -> (Pairs, Pairs) {
    let mut observed = Pairs::new();
    for cell in cells {
        let (Some(so), Some(to)) = cell.owners else {
            continue;
        };
        let ends = (tree.child_under(level, so), tree.child_under(level, to));
        if let (Some(s), Some(t)) = ends {
            if s != t {
                let row = observed.entry((s, t)).or_insert((0, "PASS"));
                *row = (row.0 + cell.count, worse(row.1, cell.status));
            }
        }
    }
    let mut permitted = Pairs::new();
    for (source, target, imports) in declared {
        let ends = (
            tree.child_under(level, *source),
            tree.child_under(level, *target),
        );
        if let (Some(s), Some(t)) = ends {
            if s != t {
                permitted.entry((s, t)).or_insert((0, "PASS")).0 += imports;
            }
        }
    }
    (observed, permitted)
}

/// The rows of all levels: the system and each node that has children or modules.
pub(super) fn levels(
    frame: &Frame,
    topology: &Topology,
    tree: &Tree,
    found: &[Finding],
    refs: &mut Refs,
) -> Levels {
    let cells = cells(frame, topology, tree, found);
    let (modules, assignments) = modules(topology, tree, &cells, refs);
    let ids: BTreeMap<&str, usize> = tree
        .nodes
        .iter()
        .enumerate()
        .map(|(i, n)| (n.id.as_str(), i))
        .collect();
    let declared: Vec<(usize, usize, usize)> = topology
        .requires
        .iter()
        .filter_map(|r| {
            Some((
                *ids.get(r.source.as_str())?,
                *ids.get(r.target.as_str())?,
                r.imports,
            ))
        })
        .collect();
    // The crossings between the parts of a system: an edge with no import site, named by its title.
    let crossings: Vec<(usize, usize, &super::frame::Interface)> = frame
        .interfaces
        .iter()
        .filter_map(|i| {
            Some((
                *ids.get(format!("PART:{}", i.source).as_str())?,
                *ids.get(format!("PART:{}", i.target).as_str())?,
                i,
            ))
        })
        .collect();
    let mut out = Levels {
        modules,
        assignments,
        cells: Vec::new(),
        rows: Vec::new(),
        deviations: Vec::new(),
        balance: Value::Null,
        requires: BTreeMap::new(),
        used_by: BTreeMap::new(),
    };
    let complete = if topology.complete { "PASS" } else { "UNKNOWN" };
    let reason = if topology.complete {
        "The scan names each import between the modules."
    } else {
        "The scan has gaps: some imports may be missing."
    };
    let opened: BTreeSet<usize> = tree
        .nodes
        .iter()
        .filter_map(|n| n.parent)
        .chain(tree.owner.values().copied())
        .collect();
    let inputs = Inputs {
        tree,
        cells: &cells,
        declared: &declared,
        crossings: &crossings,
    };
    let parents = std::iter::once(None).chain(opened.into_iter().map(Some));
    for level in parents {
        let row = level_row(level, &inputs, found, &mut out);
        out.rows.push(json!({
            "parent_id": level.map(|l| &tree.nodes[l].id), "import_status": complete,
            "import_reason": reason, "questions": [], "balance": row.balance,
            "component_ids": row.children, "edges": row.edges, "modules": row.modules,
            "cells": row.cells, "finding_ids": row.findings, "deviation_ids": row.deviations,
        }));
        if level.is_none() {
            out.balance = row.balance;
        }
    }
    out.cells = cells
        .iter()
        .map(|c| json!([c.source, c.target, c.count, c.status, [], c.findings, []]))
        .collect();
    out
}

struct Row {
    children: Vec<String>,
    edges: Vec<Value>,
    modules: Vec<usize>,
    cells: Vec<usize>,
    findings: Vec<usize>,
    deviations: Vec<String>,
    balance: Value,
}

/// What each level reads: the tree, the observed cells, the declared requirements and the crossings.
struct Inputs<'a> {
    tree: &'a Tree,
    cells: &'a [Cell],
    declared: &'a [(usize, usize, usize)],
    crossings: &'a [(usize, usize, &'a super::frame::Interface)],
}

fn level_row(
    level: Option<usize>,
    inputs: &Inputs<'_>,
    found: &[Finding],
    out: &mut Levels,
) -> Row {
    let Inputs {
        tree,
        cells,
        declared,
        crossings,
    } = *inputs;
    let (observed, permitted) = pairs(level, tree, cells, declared);
    let id = |n: usize| tree.nodes[n].id.clone();
    let level_id = level.map(id);
    let mut deviations = Vec::new();
    let mut deviation = |kind: &str, (s, t): (usize, usize), out: &mut Levels| {
        let name = format!("deviation-{}", out.deviations.len());
        out.deviations.push(json!({"id": name, "kind": kind, "level_id": level_id, "source_id": id(s), "target_id": id(t)}));
        deviations.push(name);
    };
    for pair in observed.keys().filter(|p| !permitted.contains_key(p)) {
        deviation("undeclared", *pair, out);
    }
    let unused: Vec<(usize, usize)> = permitted
        .iter()
        .filter(|(p, row)| row.0 == 0 && !observed.contains_key(p))
        .map(|(p, _)| *p)
        .collect();
    for pair in &unused {
        deviation("allowed_unused", *pair, out);
    }
    for ((s, t), (imports, _)) in &permitted {
        out.requires.entry(*s).or_default().push((*t, *imports));
    }
    for ((s, t), (sites, _)) in &observed {
        out.used_by.entry(*t).or_default().push((*s, *sites));
    }
    let inside =
        |owner: Option<usize>| owner.is_some_and(|o| tree.inside(level, o)) || level.is_none();
    let used = permitted
        .keys()
        .filter(|p| observed.contains_key(p))
        .count();
    Row {
        children: (0..tree.nodes.len()).filter(|n| tree.nodes[*n].parent == level).map(id).collect(),
        edges: observed
            .iter()
            .map(|((s, t), (sites, status))| json!({"source_id": id(*s), "target_id": id(*t), "import_sites": sites, "status": status}))
            .chain(crossings.iter().filter_map(|(s, t, i)| {
                let ends = (tree.child_under(level, *s)?, tree.child_under(level, *t)?);
                (ends.0 != ends.1 && !observed.contains_key(&ends)).then(|| json!({
                    "source_id": id(ends.0), "target_id": id(ends.1), "import_sites": 0,
                    "status": "PASS", "crossing": i.title, "schema": i.schema,
                }))
            }))
            .collect(),
        modules: (0..out.modules.len())
            .filter(|m| inside(out.modules[*m]["id"].as_str().and_then(|n| tree.owner.get(n).copied())))
            .collect(),
        cells: (0..cells.len()).filter(|c| inside(cells[*c].owners.0) && inside(cells[*c].owners.1)).collect(),
        findings: (0..found.len())
            .filter(|f| found[*f].modules.iter().any(|m| inside(tree.owner.get(m).copied())))
            .collect(),
        deviations,
        balance: json!({"declared": permitted.len(), "used": used,
            "undeclared": observed.len() - observed.keys().filter(|p| permitted.contains_key(p)).count(),
            "allowed_unused": unused.len()}),
    }
}
