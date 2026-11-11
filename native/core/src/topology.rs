// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rows of the sections of slice S3: `dependency_edges`, `modules`, `packages` and `cycles`.
//!
//! Reference engine: `check/evaluation/topology.py` `aggregate_edges`, `module_records`,
//! `package_records` and `cycle_sections`, with `count_macro_bodies` and the `symbol_count` of
//! `evaluate_source`. Each row is the 2.9 row of `classified` (`ir/source_records.py`): the
//! subjects without an empty name and sorted, the id lists sorted. Each section is sorted by id.
//! The rows need only the reply part of the model (`Graph`), so a run whose contract the core
//! cannot use yet still has them.

use archkeel_model::{Cycle, Edge, Graph, Level, Section};
use serde_json::{json, Value};

/// The sections of slice S3.
const OWNED: [Section; 4] = [
    Section::DependencyEdges,
    Section::Modules,
    Section::Packages,
    Section::Cycles,
];

/// True for a section of slice S3.
pub(crate) fn owns(section: Section) -> bool {
    OWNED.contains(&section)
}

/// The rows of a section of slice S3, or `None` for another section.
pub(crate) fn rows(graph: &Graph, section: Section) -> Option<Vec<Value>> {
    let mut rows = match section {
        Section::DependencyEdges => [Level::Package, Level::Module]
            .into_iter()
            .flat_map(|level| graph.edges(level).iter().map(edge_row))
            .collect(),
        Section::Modules => module_rows(graph),
        Section::Packages => package_rows(graph),
        Section::Cycles => graph.cycles().iter().map(cycle_row).collect(),
        _ => return None,
    };
    // A stable sort by id, as `sorted(..., key=lambda item: item["id"])`.
    rows.sort_by(|a: &Value, b: &Value| a["id"].as_str().cmp(&b["id"].as_str()));
    Some(rows)
}

/// The fields of `classified` that every row of this file has: `[id, area, kind, title]`, the
/// subjects, the evidence ids and the fact ids.
fn record(
    names: [&str; 4],
    subjects: &[&str],
    evidence: &[&str],
    facts: &[&str],
    data: Value,
) -> Value {
    let [id, area, kind, title] = names;
    json!({
        "id": id,
        "evidence_class": "FACT",
        "area": area,
        "kind": kind,
        "title": title,
        "subjects": sorted(subjects.iter().copied().filter(|name| !name.is_empty()).collect()),
        "evidence_ids": sorted(evidence.to_vec()),
        "rule_ids": [],
        "fact_ids": sorted(facts.to_vec()),
        "provenance": [],
        "data": data,
    })
}

fn sorted(mut names: Vec<&str>) -> Vec<&str> {
    names.sort_unstable();
    names
}

/// The row of an edge (`aggregate_edges`).
fn edge_row(edge: &Edge) -> Value {
    let level = edge.level().name();
    let (source, target) = (edge.source(), edge.target());
    let facts: Vec<&str> = edge.imports().iter().map(String::as_str).collect();
    record(
        [
            edge.id(),
            &format!("{level}_topology"),
            &format!("{level}_dependency"),
            &format!("{source} \u{2192} {target}"),
        ],
        &[source, target],
        &[],
        &facts,
        json!({
            "level": level,
            "source": source,
            "target": target,
            "count": edge.imports().len(),
            "type_checking_count": edge.type_checking(),
            "runtime_count": edge.runtime(),
            "source_rank": edge.source_rank(),
            "target_rank": edge.target_rank(),
            "bidirectional": edge.bidirectional(),
        }),
    )
}

/// The rows of the modules (`module_records` and `count_macro_bodies`).
fn module_rows(graph: &Graph) -> Vec<Value> {
    graph
        .modules()
        .iter()
        .map(|(id, module)| {
            let package = graph
                .packages()
                .get(module.package())
                .map_or("", |p| p.name());
            let measure = graph.module_measure(id);
            record(
                [module.fact_id(), "module_topology", "module", module.name()],
                &[module.name(), package],
                &[module.evidence()],
                &[],
                json!({
                    "qualified_name": module.name(),
                    "package": package,
                    "file": module.file(),
                    "symbol_count": graph.symbol_count(id),
                    "fan_in": measure.fan_in(),
                    "fan_out": measure.fan_out(),
                    "rank": measure.rank(),
                    "all_exports": module.exports(),
                    "all_literal": module.exports_literal(),
                    "compatibility_logic_free": module.compatibility_logic_free(),
                }),
            )
        })
        .collect()
}

/// The rows of the packages (`package_records`).
fn package_rows(graph: &Graph) -> Vec<Value> {
    let edges = graph.edges(Level::Package);
    graph
        .packages()
        .iter()
        .map(|(id, package)| {
            let name = package.name();
            let modules: Vec<&str> = package
                .modules()
                .iter()
                .filter_map(|&module| graph.modules().get(module))
                .map(|module| module.fact_id())
                .collect();
            let dependencies: Vec<&str> = sorted(
                edges
                    .iter()
                    .filter(|edge| edge.source() == name)
                    .map(Edge::target)
                    .collect(),
            );
            let measure = graph.package_measure(id);
            record(
                [package.fact_id(), "package_topology", "package", name],
                &[name],
                &[],
                &modules,
                json!({
                    "qualified_name": name,
                    "module_count": modules.len(),
                    "fan_in": measure.fan_in(),
                    "fan_out": measure.fan_out(),
                    "rank": measure.rank(),
                    "dependencies": dependencies,
                }),
            )
        })
        .collect()
}

/// The row of a cycle (`_cycle_records`, and `_backed_package_cycles` for a package cycle).
fn cycle_row(cycle: &Cycle) -> Value {
    let level = cycle.level().name();
    let members: Vec<&str> = cycle.members().iter().map(String::as_str).collect();
    let edges: Vec<&str> = cycle.internal_edges().iter().map(String::as_str).collect();
    let mut title = format!(
        "{} cycle with {} members",
        capitalized(level),
        members.len()
    );
    let mut data = json!({"level": level, "members": members, "internal_edges": edges});
    if let Some(backed_by) = cycle.backed_by() {
        if backed_by.is_empty() {
            title.push_str(", roll-up only: no module cycle crosses them");
        }
        data["backed_by"] = json!(backed_by);
    }
    record(
        [cycle.id(), "cycles", &format!("{level}_scc"), &title],
        &members,
        &[],
        &edges,
        data,
    )
}

/// The level word with a capital first letter (`str.capitalize` of an ASCII word).
fn capitalized(word: &str) -> String {
    let mut letters = word.chars();
    letters.next().map_or_else(String::new, |first| {
        first.to_ascii_uppercase().to_string() + letters.as_str()
    })
}
