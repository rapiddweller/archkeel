// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the Explorer (AD-606): the frame in the payload shape that the 4.0.1 Explorer
//! reads. Each value is a row of the frame or a count of rows; the page decides no verdict. A
//! component is FAIL when a violated place lies inside it, UNKNOWN when a gap names a module
//! inside it, else the floor of the run: PASS only when the run decides every rule (AD-730).

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{json, Value};

use super::atlas_levels::{levels, Levels};
use super::atlas_tree::{held, Finding, Node, Refs, Tree};
use super::cases::{one_line, Names};
use super::frame::{Frame, Topology};
use super::places::{Kind, Places};
use super::status::{node_status, run_word, Floors, Shown};
use crate::head::RuleVerdict;

fn findings(frame: &Frame, places: &Places, names: &Names<'_>, refs: &mut Refs) -> Vec<Finding> {
    let mut found = Vec::new();
    for place in &places.shown {
        let (modules, pair, evidence) = match &place.kind {
            Kind::Import {
                source,
                target,
                evidence,
            } => (
                vec![source.clone()],
                target.as_ref().map(|t| (source.clone(), t.clone())),
                evidence.first().cloned(),
            ),
            Kind::Cycle(cycle) => (
                cycle.members.clone(),
                None,
                cycle.path.first().and_then(|s| s.evidence.first().cloned()),
            ),
        };
        let at = evidence.and_then(|e| frame.locations.get(&e).cloned());
        let rules: Vec<&str> = place.rules.iter().map(|r| r.rule.as_str()).collect();
        let kind = rules
            .first()
            .and_then(|r| frame.rules.get(*r))
            .map_or("", |row| row.0.as_str());
        let cause = place.rules.first().map_or("", |r| r.cause.as_str());
        found.push(Finding {
            value: json!({
                "id": format!("x{}", place.number), "kind": kind, "rule_ids": rules,
                "title": one_line(names, place), "remedy_ref": refs.id(cause),
                "path": at.as_ref().map(|l| l.path.clone()), "line": at.map(|l| l.line),
            }),
            modules,
            pair,
        });
    }
    found
}

/// The FAIL and UNKNOWN counts of each node, from the places and the gaps inside it.
fn exceptions(frame: &Frame, tree: &Tree, found: &[Finding]) -> (Vec<usize>, Vec<usize>) {
    let topology = frame.topology.as_ref();
    let paths: BTreeMap<&str, &str> = topology
        .into_iter()
        .flat_map(|t| &t.modules)
        .map(|m| (m.path.as_str(), m.name.as_str()))
        .collect();
    let all = tree.nodes.len();
    // The nodes that own the modules of a subject list; `None` when the list is empty or a module
    // has no owner: that subject is unscoped.
    let owners = |subjects: &[&str]| -> Option<BTreeSet<usize>> {
        let mut nodes = BTreeSet::new();
        for subject in subjects {
            let module = paths.get(subject).copied().unwrap_or(subject);
            nodes.extend(tree.chain(*tree.place.get(module)?));
        }
        (!nodes.is_empty()).then_some(nodes)
    };
    let (mut fail, mut unknown) = (vec![0; all], vec![0; all]);
    for finding in found {
        let modules: Vec<&str> = finding.modules.iter().map(String::as_str).collect();
        for node in owners(&modules).unwrap_or_default() {
            fail[node] += 1;
        }
    }
    // A gap that no node owns may hold any node: it counts for every node, so no node shows PASS
    // beside a gap that it cannot exclude.
    let mut gap_nodes = |subjects: &[&str]| {
        for node in owners(subjects).unwrap_or_else(|| (0..all).collect()) {
            unknown[node] += 1;
        }
    };
    for gap in &frame.collection_gaps {
        let subjects: Vec<&str> = gap.subjects.iter().map(String::as_str).collect();
        gap_nodes(&subjects);
    }
    for (source, target) in held(frame) {
        gap_nodes(&[source.as_str(), target.as_str()]);
    }
    (fail, unknown)
}

/// The line that Target and Diff show when the contract declares no dependency: the number of open
/// dependency decisions comes from the gap that names them (`null` when the contract declares one).
fn declared_note(frame: &Frame, topology: &Topology) -> Option<String> {
    if !topology.requires.is_empty() {
        return None;
    }
    const OPEN: &str = " open dependency decisions";
    let open = frame.named.values().find_map(|reason| {
        let before = &reason[..reason.find(OPEN)?];
        let digits: String = before
            .chars()
            .rev()
            .take_while(char::is_ascii_digit)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect();
        digits.parse::<usize>().ok()
    });
    Some(match open {
        Some(n) => {
            format!("The contract declares no dependencies yet: {n} open dependency decisions.")
        }
        None => "The contract declares no dependencies yet.".to_owned(),
    })
}

/// The `requires` entries of a node: a component lists its own entries, with their rationale and
/// ports; a layer lists the pairs of its components, rolled up to the layers.
fn requires(
    i: usize,
    tree: &Tree,
    levels: &Levels,
    topology: &Topology,
    refs: &mut Refs,
) -> Vec<Value> {
    let node = &tree.nodes[i];
    if node.rank.is_some() {
        let rolled = refs.id("Declared between components of the two layers.");
        return levels
            .requires(i)
            .iter()
            .map(|(target, imports)| json!({
                "id": format!("REQ:{}>{}", node.id, tree.nodes[*target].id), "target_id": target,
                "observed_imports": imports, "rationale_ref": rolled, "decided_by": "architect", "through": [],
            }))
            .collect();
    }
    topology
        .requires
        .iter()
        .filter(|r| r.source == node.id)
        .filter_map(|r| {
            let target = tree.nodes.iter().position(|n| n.id == r.target)?;
            Some(json!({
                "id": format!("REQ:{}>{}", r.source, r.target), "target_id": target,
                "observed_imports": r.imports, "rationale_ref": refs.id(&r.rationale),
                "decided_by": "architect", "through": r.through,
            }))
        })
        .collect()
}

/// The status of each box and whether a gap of its own holds it, in the order of the boxes.
pub(super) type Marks = Vec<(Shown, bool)>;

fn components(
    tree: &Tree,
    levels: &Levels,
    frame: &Frame,
    found: &[Finding],
    refs: &mut Refs,
) -> (Vec<Value>, Marks) {
    let (fail, unknown) = exceptions(frame, tree, found);
    let floors = Floors::of(frame);
    let floor = |i: usize| floors.at(tree, Some(i));
    let marks: Marks = (0..tree.nodes.len())
        .map(|i| (node_status(floor(i), fail[i], unknown[i]).0, unknown[i] > 0))
        .collect();
    let mut modules = vec![0usize; tree.nodes.len()];
    for owner in tree.place.values() {
        for node in tree.chain(*owner) {
            modules[node] += 1;
        }
    }
    let empty = Topology::default();
    let topology = frame.topology.as_ref().unwrap_or(&empty);
    let rows = (0..tree.nodes.len())
        .map(|i| {
            let node = &tree.nodes[i];
            let (state, reason) = node_status(floor(i), fail[i], unknown[i]);
            // A layer is no component of the contract: it states no surface.
            let public = (node.rank.is_none() || !node.public.is_empty())
                .then(|| node.public.iter().map(|p| refs.id(p)).collect::<Vec<_>>());
            let requires = requires(i, tree, levels, topology, refs);
            let language = (!tree.languages[i].is_empty())
                .then(|| tree.languages[i].iter().cloned().collect::<Vec<_>>().join(" + "));
            json!({
                "id": node.id, "label": archkeel_facts::identity::readable(&node.label), "parent_id": node.parent.map(|p| &tree.nodes[p].id),
                "layer": node.layer, "layer_rank": node.rank, "path": archkeel_facts::identity::readable(&node.path), "scope": node.label,
                "status": state, "language": language, "reason_ref": refs.id(&reason),
                "observed_modules": modules[i], "observed_symbols": null, "symbols_complete": false,
                "public": public, "requires": requires, "used_by": levels.used_by(i),
                "responsibilities": node.about, "not_responsible_for": node.forbidden,
                "planned": (!node.planned.is_empty()).then_some(&node.planned),
                "provenance": node.provenance.iter().map(|p| refs.id(p)).collect::<Vec<_>>(), "groups": node.members,
                "directory": node.directory, "decided_by": Node::decided_by(node),
            })
        })
        .collect();
    (rows, marks)
}

/// The ports of each `requires` entry as declared boundary permissions: an import of the pair
/// must pass through one of them. The frame names no applied port.
fn permissions(topology: &Topology) -> Vec<Value> {
    topology
        .requires
        .iter()
        .flat_map(|r| {
            r.through.iter().enumerate().map(move |(n, selector)| {
                json!({
                    "id": format!("PORT:{}>{}:{n}", r.source, r.target), "rule_id": "requires",
                    "component_ids": [r.source, r.target], "qualified_name": selector,
                    "position": format!("through, {} to {}", r.source, r.target),
                    "rationale": r.rationale, "decided_by": "architect", "source": "contract",
                    "contract_scope_id": null, "rule_ids": [], "fact_ids": [], "evidence_ids": [],
                    "provenance": [], "locations": [], "routes": [],
                })
            })
        })
        .collect()
}

/// A finding of a rule kind in plain words, for one and for many: the sheet of a box says `5 public
/// names without a user (RULE-ID)`, not a bare rule id. A kind without its own words is told by its
/// contract word.
pub(super) fn plain(kind: &str) -> (String, String) {
    let words: Option<(&str, &str)> = match kind {
        "forbidden_dependency" => Some(("forbidden dependency", "forbidden dependencies")),
        "allowed_dependency" => Some((
            "dependency outside the allowed ones",
            "dependencies outside the allowed ones",
        )),
        "complete_assignment" => Some(("module in no component", "modules in no component")),
        "complete_requires" => Some((
            "undeclared dependency between components",
            "undeclared dependencies between components",
        )),
        "complete_external_scope" | "external_dependency_scope" => Some((
            "external dependency in the wrong place",
            "external dependencies in the wrong place",
        )),
        "no_component_cycles" => Some(("dependency cycle", "dependency cycles")),
        "layer_order" => Some((
            "use against the layer order",
            "uses against the layer order",
        )),
        "interface_boundary" => Some((
            "use outside the public interface",
            "uses outside the public interface",
        )),
        "unused_public" => Some(("public name without a user", "public names without a user")),
        "sibling_isolation" => Some(("use between siblings", "uses between siblings")),
        "symbol_placement" => Some(("symbol in the wrong place", "symbols in the wrong place")),
        "root_layout" => Some((
            "file outside the root layout",
            "files outside the root layout",
        )),
        _ => None,
    };
    match words {
        Some((one, many)) => (one.to_owned(), many.to_owned()),
        None => {
            let text = kind.replace('_', " ");
            (format!("finding of {text}"), format!("findings of {text}"))
        }
    }
}

fn rule_assessments(frame: &Frame, found: &[Finding], refs: &mut Refs) -> Vec<Value> {
    let whole = refs.id("whole run");
    frame
        .rules
        .iter()
        .map(|(rule, (kind, verdict))| {
            let count = found
                .iter()
                .filter(|f| f.value["rule_ids"].as_array().is_some_and(|r| r.iter().any(|x| x == rule)))
                .count();
            let reason = frame.explained.get(rule).map_or("", String::as_str);
            let (plain_one, plain_many) = plain(kind);
            json!({
                "plain_one": plain_one, "plain_many": plain_many,
                "id": refs.id(rule), "kind": refs.id(kind), "reason": refs.id(reason), "scope": whole,
                "status": verdict, "count": count, "components": [], "component_ids": [],
                "evaluation_proven": *verdict != RuleVerdict::Unknown, "evidence": [], "evidence_count": 0,
                "scope_id": null, "uncertainty_actions": [], "undecided": 0,
            })
        })
        .collect()
}

fn unknowns(frame: &Frame) -> Vec<Value> {
    let mut by_reason: BTreeMap<&str, usize> = BTreeMap::new();
    for gap in &frame.collection_gaps {
        let reason = gap.reason.split(':').next().unwrap_or(&gap.reason);
        *by_reason.entry(reason).or_default() += 1;
    }
    by_reason
        .into_iter()
        .map(|(reason, count)| json!({"count": count, "reason": reason}))
        .collect()
}

/// The payload of the Explorer and the marks of its boxes, or `None` when the frame holds no
/// topology.
pub(super) fn payload(frame: &Frame, places: &Places, names: &Names<'_>) -> Option<(Value, Marks)> {
    let topology = frame.topology.as_ref()?;
    let tree = Tree::of(topology);
    let mut refs = Refs::default();
    let found = findings(frame, places, names, &mut refs);
    let levels = levels(frame, topology, &tree, &found, &mut refs);
    let (components, marks) = components(&tree, &levels, frame, &found, &mut refs);
    let rule_assessments = rule_assessments(frame, &found, &mut refs);
    let coverage = json!([[{"entity_kinds": ["module"], "relationship_kinds": [], "scope_id": "",
        "status": "unavailable", "reason": "This version does not list symbols."}]]);
    let languages: BTreeSet<&str> = topology
        .modules
        .iter()
        .map(|m| m.language.as_str())
        .filter(|l| !l.is_empty())
        .collect();
    let note = (languages.len() == 1).then(|| {
        format!(
            "This page shows one part of the system: its {} modules. Another part has its own run and contract; a system document joins the parts into one page.",
            languages.iter().next().copied().unwrap_or_default()
        )
    });
    let home = home(frame);
    let atlas = json!({
        "repository": home["repository"], "status": run_word(frame.status), "declared_rules": run_word(frame.status),
        "result": result(frame), "reason": frame.cause,
        "source": {"git_head": frame.identity.git_head, "source_digest": frame.identity.contract_digest},
        "components": components, "modules": levels.modules, "assignments": levels.assignments,
        "cells": levels.cells, "levels": levels.rows, "deviations": levels.deviations,
        "balance": levels.balance, "findings": found.iter().map(|f| &f.value).collect::<Vec<_>>(),
        "rule_assessments": rule_assessments, "unknowns": unknowns(frame),
        "declared_note": declared_note(frame, topology),
        "unknown_count": frame.collection_gaps.len(), "questions": [], "declared_modules": [],
        "module_correspondences": [], "module_inventories": [], "symbols_complete": false,
        "symbol_coverages": coverage, "architecture_href": "#next", "detail_page": null,
        "unassigned_detail_href": null,
        "module_box_limit": super::atlas_node::ON_SCREEN,
        "cell_permission_reason_ref": refs.id("The page names no permission for one pair of modules."),
        "language_note": note,
        "reference_ids": refs.list,
    });
    let value = json!({
        "schema_version": "1.0.0", "atlas": atlas,
        "boundary_permissions": {"applied": [], "declared": permissions(topology)},
        "navigation": home,
    });
    Some((value, marks))
}

/// The result of the run in the words of its verdict: `PASS assuming <premises>` for a PASS that
/// rests on a premise of the contract (AD-764), else the run word. It replaces the 4.0.1 word
/// "observation": `topology.complete` only says that a list of the topology was cut by its budget,
/// which tells a visitor nothing about the result.
fn result(frame: &Frame) -> String {
    let premised = super::rules::qualifier(frame).filter(|_| !frame.premises.is_empty());
    match (frame.status, premised) {
        (Some(crate::head::Status::Pass), Some(words)) => words,
        (status, _) => run_word(status).to_string(),
    }
}

/// The root of the Explorer (E4, #1451): the page of a part names "<part> of <system>" and the
/// page of its system; a system page names its title; the page of one run says "System".
fn home(frame: &Frame) -> Value {
    match &frame.part_of {
        Some(link) => json!({
            "repository": format!("{} of {}", link.part, link.system), "main_href": "",
            "part_title": link.part, "system_title": link.system, "system_href": link.href,
        }),
        None if !frame.system_title.is_empty() => {
            json!({"repository": frame.system_title, "main_href": ""})
        }
        None => json!({"repository": "System", "main_href": ""}),
    }
}
