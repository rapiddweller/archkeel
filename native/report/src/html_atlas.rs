// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data of the Explorer (AD-606): the frame in the payload shape that the 4.0.1 Explorer
//! reads. Each value is a row of the frame or a count of rows; the page decides no verdict. A
//! component is FAIL when a violated place lies inside it, UNKNOWN when a gap names a module
//! inside it, else PASS.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{json, Value};

use super::atlas_levels::{levels, Levels};
use super::atlas_tree::{held, Finding, Refs, Tree};
use super::cases::{one_line, Names};
use super::frame::Frame;
use super::places::{Kind, Places};

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
    let count = |subjects: &mut dyn Iterator<Item = &str>, into: &mut Vec<usize>| {
        let mut nodes = BTreeSet::new();
        for subject in subjects {
            let module = paths.get(subject).copied().unwrap_or(subject);
            if let Some(owner) = tree.owner.get(module) {
                nodes.extend(tree.chain(*owner));
            }
        }
        for node in nodes {
            into[node] += 1;
        }
    };
    let (mut fail, mut unknown) = (vec![0; tree.nodes.len()], vec![0; tree.nodes.len()]);
    for finding in found {
        count(&mut finding.modules.iter().map(String::as_str), &mut fail);
    }
    for gap in &frame.collection_gaps {
        count(&mut gap.subjects.iter().map(String::as_str), &mut unknown);
    }
    for (source, target) in held(frame) {
        count(
            &mut [source.as_str(), target.as_str()].into_iter(),
            &mut unknown,
        );
    }
    (fail, unknown)
}

fn status(fail: usize, unknown: usize) -> (&'static str, String) {
    match (fail, unknown) {
        (0, 0) => ("PASS", "No violated place and no gap inside.".to_owned()),
        (0, gaps) => (
            "UNKNOWN",
            format!("{gaps} gaps name a module inside: a rule cannot decide here."),
        ),
        (places, _) => ("FAIL", format!("{places} violated places inside.")),
    }
}

fn components(
    tree: &Tree,
    levels: &Levels,
    frame: &Frame,
    found: &[Finding],
    refs: &mut Refs,
) -> Vec<Value> {
    let (fail, unknown) = exceptions(frame, tree, found);
    let mut modules = vec![0usize; tree.nodes.len()];
    for owner in tree.owner.values() {
        for node in tree.chain(*owner) {
            modules[node] += 1;
        }
    }
    let declared = refs.id("Declared in the contract.");
    tree.nodes
        .iter()
        .enumerate()
        .map(|(i, node)| {
            let (state, reason) = status(fail[i], unknown[i]);
            let public: Vec<usize> = node.public.iter().map(|p| refs.id(p)).collect();
            let requires: Vec<Value> = levels.requires(i).iter().map(|(target, imports)| json!({
                "id": format!("REQ:{}>{}", node.id, tree.nodes[*target].id), "target_id": target,
                "observed_imports": imports, "rationale_ref": declared, "decided_by": "architect", "through": [],
            })).collect();
            json!({
                "id": node.id, "label": node.label, "parent_id": node.parent.map(|p| &tree.nodes[p].id),
                "layer": node.layer, "path": node.path, "scope": node.label, "status": state,
                "language": (!tree.languages[i].is_empty()).then(|| tree.languages[i].iter().cloned().collect::<Vec<_>>().join(" + ")),
                "reason_ref": refs.id(&reason), "observed_modules": modules[i], "observed_symbols": null,
                "symbols_complete": false, "public": public, "requires": requires,
                "used_by": levels.used_by(i), "responsibilities": node.about, "not_responsible_for": [],
                "provenance": [], "planned": null, "decided_by": "architect",
            })
        })
        .collect()
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
            json!({
                "id": refs.id(rule), "kind": refs.id(kind), "reason": refs.id(reason), "scope": whole,
                "status": verdict, "count": count, "components": [], "component_ids": [],
                "evaluation_proven": verdict != "UNKNOWN", "evidence": [], "evidence_count": 0,
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

/// The payload of the Explorer, or `None` when the frame holds no topology.
pub(super) fn payload(frame: &Frame, places: &Places, names: &Names<'_>) -> Option<Value> {
    let topology = frame.topology.as_ref()?;
    let tree = Tree::of(topology);
    let mut refs = Refs::default();
    let found = findings(frame, places, names, &mut refs);
    let levels = levels(frame, topology, &tree, &found, &mut refs);
    let components = components(&tree, &levels, frame, &found, &mut refs);
    let rule_assessments = rule_assessments(frame, &found, &mut refs);
    let coverage = json!([[{"entity_kinds": ["module"], "relationship_kinds": [], "scope_id": "",
        "status": "unavailable", "reason": "The 5.0 frame names no symbol inventory."}]]);
    let complete = if topology.complete { "PASS" } else { "UNKNOWN" };
    let atlas = json!({
        "repository": "System", "status": frame.status, "declared_rules": frame.status,
        "observation_complete": complete, "reason": frame.cause,
        "source": {"git_head": frame.identity.git_head, "source_digest": frame.identity.contract_digest},
        "components": components, "modules": levels.modules, "assignments": levels.assignments,
        "cells": levels.cells, "levels": levels.rows, "deviations": levels.deviations,
        "balance": levels.balance, "findings": found.iter().map(|f| &f.value).collect::<Vec<_>>(),
        "rule_assessments": rule_assessments, "unknowns": unknowns(frame),
        "unknown_count": frame.collection_gaps.len(), "questions": [], "declared_modules": [],
        "module_correspondences": [], "module_inventories": [], "symbols_complete": false,
        "symbol_coverages": coverage, "architecture_href": "#next", "detail_page": null,
        "unassigned_detail_href": null,
        "cell_permission_reason_ref": refs.id("The page names no permission for one pair of modules."),
        "reference_ids": refs.list,
    });
    Some(json!({
        "schema_version": "1.0.0", "atlas": atlas,
        "boundary_permissions": {"applied": [], "declared": []},
        "navigation": {"repository": "System", "main_href": ""},
    }))
}
