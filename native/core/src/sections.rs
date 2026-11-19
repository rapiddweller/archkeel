// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `Sections` request: the rows of each requested section, or the reason that it has none.
//! The evaluator gives the violations, sorted by id (AD-360). Topology rows need no contract.

use std::collections::BTreeMap;

use archkeel_eval::{Cited, Cyclic, Layered, Outcome, Violation};
use archkeel_model::{Graph, Model, Reason, Section};
use serde_json::{json, Value};

#[cfg(test)]
#[path = "interface_row_tests.rs"]
mod interface_row_tests;
/// One requested section and its rows or the reason that it has none.
pub(crate) type SectionAnswer = (Section, Result<Vec<Value>, Reason>);
/// The derivation of a run: its reply part and its model, or the reason of each missing part.
pub(crate) type Derivation<'a> = (Result<&'a Graph, Reason>, Result<&'a Model, Reason>);

pub(crate) fn answer(
    (graph, model): Derivation<'_>,
    outcomes: &[Outcome],
    sections: &[Section],
) -> Vec<SectionAnswer> {
    // Each section has its rows built one time, also when a caller names it again.
    let mut unique: Vec<Section> = Vec::with_capacity(sections.len());
    for &section in sections {
        if !unique.contains(&section) {
            unique.push(section);
        }
    }
    unique
        .into_iter()
        .map(|section| {
            let graph_rows = graph
                .clone()
                .map(|graph| crate::topology::rows(graph, section));
            let rows = match (graph_rows, model.clone()) {
                (Ok(Some(rows)), _) => Ok(rows),
                (Err(reason), _) if crate::topology::owns(section) => Err(reason),
                (_, Ok(_)) if section == Section::Violations => Ok(violation_rows(outcomes)),
                (_, Ok(model)) => model.rows(section).map(|rows| match rows {}),
                (_, Err(reason)) => Err(reason),
            };
            (section, rows)
        })
        .collect()
}
/// The rows of the sections that have rows, and the reason of each section that has none.
pub(crate) fn split(
    answers: Vec<SectionAnswer>,
) -> (
    BTreeMap<&'static str, Vec<Value>>,
    BTreeMap<&'static str, String>,
) {
    let mut rows = BTreeMap::new();
    let mut reasons = BTreeMap::new();
    for (section, answer) in answers {
        match answer {
            Ok(found) => {
                rows.insert(section.name(), found);
            }
            Err(reason) => {
                reasons.insert(section.name(), reason.to_string());
            }
        }
    }
    (rows, reasons)
}
fn violation_rows(outcomes: &[Outcome]) -> Vec<Value> {
    let mut violations: Vec<&Violation> = outcomes
        .iter()
        .flat_map(|outcome| outcome.violations())
        .collect();
    violations.sort_by(|a, b| a.id().cmp(b.id()));
    violations.into_iter().map(row).collect()
}
/// The 2.9 row of a violation (`classified` in `ir/source_records.py`).
#[expect(
    clippy::too_many_lines,
    reason = "keep all record kinds in one exhaustive match"
)]
fn row(violation: &Violation) -> Value {
    match violation {
        Violation::Unassigned {
            id,
            rule,
            source,
            name,
            fact_id,
            evidence,
            ..
        } => record(
            [id, rule, fact_id],
            std::slice::from_ref(evidence),
            ["components", "complete_assignment"],
            &[name],
            format!("{name} is not owned by exactly one component"),
            json!({"source": source, "module": name}),
        ),
        Violation::NotAllowedChild {
            id,
            rule,
            root,
            child,
            allowed,
            fact_id,
            evidence,
            ..
        } => record(
            [id, rule, fact_id],
            std::slice::from_ref(evidence),
            ["module_topology", "root_layout"],
            &[child],
            format!("{child} is not an allowed child of {root}"),
            json!({"root": root, "child": child, "allowed_children": allowed}),
        ),
        Violation::OutsideScope {
            id,
            rule,
            dependency,
            cited,
        } => import_record(
            [id, rule],
            cited,
            "external_dependency_scope",
            format!(
                "{} imports {dependency} outside its allowed scope",
                cited.source_module
            ),
            json!({"source_module": cited.source_module, "target_module": cited.target_module,
                   "dependency": dependency}),
        ),
        Violation::Undeclared {
            id,
            rule,
            source,
            dependency,
            cited,
        } => import_record(
            [id, rule],
            cited,
            "complete_external_scope",
            format!("{} imports undeclared {dependency}", cited.source_module),
            json!({"source": source, "source_module": cited.source_module,
                   "target_module": cited.target_module, "dependency": dependency}),
        ),
        Violation::PrivateImport { .. }
        | Violation::Publication(_)
        | Violation::Forbidden { .. }
        | Violation::Peer { .. }
        | Violation::Unrequired { .. } => direction_record(violation),
        Violation::OuterLayer(layered) => layer_record(layered),
        Violation::Cycle(cyclic) => cycle_record(cyclic),
        Violation::Construct(row) => archkeel_report::construct_row(row),
        Violation::ProtocolDeclaration(row) => record(
            [&row.id, &row.rule, &row.id],
            &row.evidence,
            ["source", "protocol_declarations"],
            &[&row.qualified_name, &row.subject],
            format!("{} does not name the canonical Protocol", row.subject),
            json!({"member": row.subject, "annotation": row.text}),
        ),
        Violation::BoundaryType(found) => record(
            [&found.id, &found.rule, &found.id],
            &found.evidence,
            ["source", "boundary_types"],
            &[&found.qualified_name, &found.subject],
            format!(
                "{} breaks the boundary types: {}",
                found.subject, found.text
            ),
            json!({"qualified_name": found.qualified_name, "position": found.position,
                   "annotation": found.text, "reasons": found.reasons}),
        ),
        Violation::SymbolPlacement(found) => placement_record(found),
        Violation::CallOwner {
            id,
            rule,
            fact,
            source,
            target,
            evidence,
        } => record(
            [id, rule, fact],
            evidence,
            ["calls", "call_owner"],
            &[source, target],
            format!("{source} invokes {target} outside its owner"),
            json!({"source_scope": source, "target": target}),
        ),
        Violation::ForbiddenArgument {
            id,
            rule,
            fact,
            source,
            target,
            parameter,
            evidence,
        } => record(
            [id, rule, fact],
            evidence,
            ["source", "forbidden_call_argument"],
            &[source, target],
            format!("{source} passes a written string literal to {target}.{parameter}"),
            json!({"source_scope": source, "target": target, "parameter": parameter}),
        ),
        Violation::UnusedPublic(found) => {
            let item = format!("{}:{}", found.module, found.name);
            let data = json!({"module": found.module, "name": found.name, "item_kind": found.kind});
            let title = format!("{item} is public and no other component uses it");
            let subjects = [&found.module, &found.name];
            record(
                [&found.id, &found.rule, &found.id],
                &found.evidence,
                ["source", "unused_public"],
                &subjects,
                title,
                data,
            )
        }
    }
}
fn placement_record(found: &archkeel_eval::PlacedClass) -> Value {
    record(
        [&found.id, &found.rule, &found.fact_id],
        &found.evidence,
        ["source", "symbol_placement"],
        &[&found.name, &found.module],
        format!("{} is outside the allowed modules", found.name),
        json!({"qualified_name": found.name, "module": found.module, "class_kind": found.kind}),
    )
}
/// A `no_component_cycles` record (slice S7, AD-384): a component cycle has the kind of its rule
/// and the members; a module cycle has the kind `module_cycle` and its edges.
fn cycle_record(cyclic: &Cyclic) -> Value {
    let Cyclic {
        id,
        rule,
        members,
        facts,
        evidence,
        edges,
        path: _,
    } = cyclic;
    let joined = members.join(" \u{2194} ");
    let (kind, title, data) = match edges {
        None => (
            "no_component_cycles",
            format!("Component cycle: {joined}"),
            json!({"members": members}),
        ),
        Some(edges) => (
            "module_cycle",
            format!("Module cycle: {joined}"),
            json!({"members": members, "edges": edges}),
        ),
    };
    let mut subjects: Vec<&str> = members
        .iter()
        .map(String::as_str)
        .filter(|m| !m.is_empty())
        .collect();
    subjects.sort_unstable();
    json!({
        "id": id,
        "evidence_class": "VIOLATION",
        "area": "cycles",
        "kind": kind,
        "title": title,
        "subjects": subjects,
        "evidence_ids": evidence,
        "rule_ids": [rule],
        "fact_ids": facts,
        "provenance": [],
        "data": data,
    })
}
/// The record of a direction violation that cites one import (slice S5, AD-380).
fn direction_record(violation: &Violation) -> Value {
    match violation {
        Violation::PrivateImport {
            id,
            rule,
            cited,
            symbol,
            source_component,
            target_component,
        } => interface_record(
            [id, rule],
            cited,
            symbol.as_deref(),
            [source_component, target_component],
        ),
        // AD-608: the subject is the published name in the module of the re-export.
        Violation::Publication(found) => {
            let archkeel_eval::Published {
                id,
                rule,
                cited,
                name,
                component,
            } = found.as_ref();
            let target = format!("{}:{name}", cited.source_module);
            named_record(
                [id, rule],
                cited,
                ["api_surface", "interface_boundary"],
                &target,
                format!(
                    "{} publishes {target} outside its declared interface",
                    cited.source_module
                ),
                json!({"symbol": name, "source_component": component, "published": true}),
            )
        }
        Violation::Forbidden {
            id,
            rule,
            cited,
            symbol,
            under_type_checking,
        } => {
            let target = target_name(cited, symbol.as_deref());
            named_record(
                [id, rule],
                cited,
                ["dependency_violations", "forbidden_dependency"],
                &target,
                format!("{} imports forbidden {target}", cited.source_module),
                json!({"symbol": symbol, "under_type_checking": under_type_checking}),
            )
        }
        Violation::Peer {
            id,
            rule,
            cited,
            source,
        } => import_record(
            [id, rule],
            cited,
            "sibling_isolation",
            format!(
                "{} imports its peer {}",
                cited.source_module, cited.target_module
            ),
            json!({"source_module": cited.source_module, "target_module": cited.target_module,
                   "source": source}),
        ),
        Violation::Unrequired {
            id,
            rule,
            cited,
            source_component,
            target_component,
        } => import_record(
            [id, rule],
            cited,
            "complete_requires",
            format!("{source_component} imports {target_component} without requiring it"),
            json!({"source_module": cited.source_module, "target_module": cited.target_module,
                   "source_component": source_component, "target_component": target_component}),
        ),
        _ => row(violation),
    }
}
/// Cite the rule receipt, contract file and source component provenance.
fn layer_record(layered: &Layered) -> Value {
    let Layered {
        id,
        rule,
        receipt,
        evidence,
        provenance,
        source_component,
        target_component,
        source_layer,
        target_layer,
        rationale,
    } = layered;
    json!({
        "id": id,
        "evidence_class": "VIOLATION",
        "area": "components",
        "kind": "layer_order",
        "title": format!(
            "{source_component} ({source_layer}) requires outer {target_component} ({target_layer})"
        ),
        "subjects": sorted_subjects(&[source_component, target_component]),
        "evidence_ids": [evidence],
        "rule_ids": [rule],
        "fact_ids": [receipt],
        "provenance": provenance,
        "data": {"source_component": source_component, "target_component": target_component,
                 "source_layer": source_layer, "target_layer": target_layer,
                 "rationale": rationale},
    })
}
/// The target name of an import, with an optional nonempty symbol.
fn target_name(cited: &Cited, symbol: Option<&str>) -> String {
    [cited.target_module.as_str(), symbol.unwrap_or("")]
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(".")
}
/// An interface violation retains the named target and both components.
fn interface_record(
    ids: [&str; 2],
    cited: &Cited,
    symbol: Option<&str>,
    components: [&str; 2],
) -> Value {
    let [id, rule] = ids;
    let [source_component, target_component] = components;
    let target = target_name(cited, symbol);
    named_record(
        [id, rule],
        cited,
        ["api_surface", "interface_boundary"],
        &target,
        format!(
            "{} reaches {target} outside its declared interface",
            cited.source_module
        ),
        json!({"symbol": symbol, "source_component": source_component, "target_component": target_component}),
    )
}
/// The common import fields of a violation that names a symbol.
fn named_record(
    ids: [&str; 2],
    cited: &Cited,
    names: [&str; 2],
    target: &String,
    title: String,
    mut data: Value,
) -> Value {
    data["source_module"] = json!(cited.source_module);
    data["target_module"] = json!(cited.target_module);
    let [id, rule] = ids;
    record(
        [id, rule, &cited.import],
        &cited.evidence,
        names,
        &[&cited.source_module, target],
        title,
        data,
    )
}
/// A violation record that cites one import: its subjects are the two modules of the import.
fn import_record(ids: [&str; 2], cited: &Cited, kind: &str, title: String, data: Value) -> Value {
    let [id, rule] = ids;
    record(
        [id, rule, &cited.import],
        &cited.evidence,
        ["dependency_violations", kind],
        &[&cited.source_module, &cited.target_module],
        title,
        data,
    )
}
/// Build a violation record with its cited fact, evidence, area, kind and subjects.
fn record(
    ids: [&str; 3],
    evidence: &[String],
    names: [&str; 2],
    subjects: &[&String],
    title: String,
    data: Value,
) -> Value {
    let [id, rule, fact_id] = ids;
    let [area, kind] = names;
    json!({
        "id": id,
        "evidence_class": "VIOLATION",
        "area": area,
        "kind": kind,
        "title": title,
        "subjects": sorted_subjects(subjects),
        "evidence_ids": evidence,
        "rule_ids": [rule],
        "fact_ids": [fact_id],
        "provenance": [],
        "data": data,
    })
}
/// `classified` drops an empty subject and sorts the others.
fn sorted_subjects<'a>(names: &[&'a String]) -> Vec<&'a str> {
    let mut found: Vec<&str> = names
        .iter()
        .map(|name| name.as_str())
        .filter(|name| !name.is_empty())
        .collect();
    found.sort_unstable();
    found
}
