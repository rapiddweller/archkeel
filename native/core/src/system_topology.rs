// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The topology and the explanation of a system run (AD-618): the rows of each part stay as they
//! are, and each part is one top component that holds the top components of its own contract. The
//! language of each module is the collector value of its part. No id may name two things: a
//! component, a module or a rule that two parts use refuses the run.

use std::collections::{BTreeSet, HashMap};

use archkeel_collect::SystemPart;
use serde_json::{json, Map, Value};

/// The part box of the Explorer for a part, from the keys of a component of the topology. The
/// texts are the ones of the system document: what the part is for, what it is not for, and what
/// it provides.
fn part_component(part: &SystemPart, sample: &Map<String, Value>) -> Value {
    let mut row: Map<String, Value> = sample
        .keys()
        .map(|key| (key.clone(), Value::Null))
        .collect();
    for key in ["packages", "exact_modules", "planned_public", "provenance"] {
        row.insert(key.to_owned(), json!([]));
    }
    row.insert("id".to_owned(), json!(format!("PART:{}", part.id)));
    row.insert("name".to_owned(), json!(part.title));
    row.insert("planned".to_owned(), json!(false));
    row.insert("public".to_owned(), json!(part.provides));
    row.insert("responsibilities".to_owned(), json!(part.responsibilities));
    row.insert(
        "forbidden_responsibilities".to_owned(),
        json!(part.forbidden_responsibilities),
    );
    Value::Object(row)
}

fn rows<'a>(topology: &'a Map<String, Value>, key: &str) -> &'a [Value] {
    topology
        .get(key)
        .and_then(Value::as_array)
        .map_or(&[], Vec::as_slice)
}

fn unique(seen: &mut BTreeSet<String>, kind: &str, id: Option<&str>) -> Result<(), String> {
    let id = id.ok_or_else(|| format!("system: a {kind} without a name"))?;
    if seen.insert(id.to_owned()) {
        Ok(())
    } else {
        Err(format!("system: two parts name the {kind} {id}"))
    }
}

/// The most evidence rows that one edge lists (`topology_projection.rs`).
const MAX_EVIDENCE: usize = 5;

/// One row for each id: the edges `unowned -> external` and the like name no component of a part,
/// so each part writes its own row with the same id. A scan of all parts would hold one row with
/// the sum of the counts, the evidence of both and the rules of both.
fn merge_edges(rows: Vec<Value>) -> Vec<Value> {
    let mut merged: Vec<Value> = Vec::new();
    let mut place: HashMap<String, usize> = HashMap::new();
    for row in rows {
        let id = row["id"].as_str().unwrap_or_default().to_owned();
        let Some(&at) = place.get(&id) else {
            place.insert(id, merged.len());
            merged.push(row);
            continue;
        };
        let held = &mut merged[at];
        let sum = |key: &str, held: &Value| {
            held[key].as_u64().unwrap_or(0) + row[key].as_u64().unwrap_or(0)
        };
        held["count"] = json!(sum("count", held));
        // A location that both rows list counts once, so the total stays the size of the set.
        let shared = union(held, &row, "evidence", MAX_EVIDENCE) as u64;
        held["evidence_total"] = json!(sum("evidence_total", held) - shared);
        let _ = union(held, &row, "rules", usize::MAX);
    }
    merged
}

/// Add the items of `row[key]` that `held[key]` lacks, up to `cap` items. It returns the number
/// of items that both hold.
fn union(held: &mut Value, row: &Value, key: &str, cap: usize) -> usize {
    let mut items = held[key].as_array().cloned().unwrap_or_default();
    let mut shared = 0;
    for item in row[key].as_array().into_iter().flatten() {
        if items.contains(item) {
            shared += 1;
        } else if items.len() < cap {
            items.push(item.clone());
        }
    }
    held[key] = json!(items);
    shared
}

/// The topology of the system. `None` when no part states one (a part without it is a gap that
/// the frame of the part names).
pub(crate) fn topology(
    parts: &[(&SystemPart, &Map<String, Value>)],
    open: Option<&str>,
) -> Result<Option<Value>, String> {
    let (mut components, mut modules) = (Vec::new(), Vec::new());
    let mut lists: [Vec<Value>; 5] = Default::default();
    let (mut ids, mut names) = (BTreeSet::new(), BTreeSet::new());
    let (mut complete, mut truncated, mut found) = (true, false, false);
    let mut totals = Map::new();
    for (part, frame) in parts {
        let Some(topology) = frame.get("topology").and_then(Value::as_object) else {
            complete = false;
            continue;
        };
        found = true;
        complete &= topology.get("complete").and_then(Value::as_bool) == Some(true);
        truncated |= topology.get("truncated").and_then(Value::as_bool) == Some(true);
        let own = rows(topology, "components");
        let Some(sample) = own.first().and_then(Value::as_object) else {
            continue;
        };
        let part_id = format!("PART:{}", part.id);
        unique(&mut ids, "component", Some(&part_id))?;
        components.push(part_component(part, sample));
        for component in own {
            let mut component = component.clone();
            unique(&mut ids, "component", component["id"].as_str())?;
            if component["parent"].is_null() {
                component["parent"] = json!(part_id);
            }
            components.push(component);
        }
        for module in rows(topology, "modules") {
            unique(&mut names, "module", module["name"].as_str())?;
            modules.push(module.clone());
        }
        for (slot, key) in [
            (0, "edges"),
            (1, "component_edges"),
            (2, "requires"),
            (4, "gaps"),
        ] {
            lists[slot].extend(rows(topology, key).iter().cloned());
        }
        for mut layer in rows(topology, "layers").iter().cloned() {
            layer["part"] = json!(part_id);
            lists[3].push(layer);
        }
        for (key, value) in topology
            .get("total")
            .and_then(Value::as_object)
            .into_iter()
            .flatten()
        {
            let sum =
                value.as_u64().unwrap_or(0) + totals.get(key).and_then(Value::as_u64).unwrap_or(0);
            totals.insert(key.clone(), json!(sum));
        }
    }
    if !found {
        return Ok(None);
    }
    totals.insert("components".to_owned(), json!(components.len()));
    totals.insert("modules".to_owned(), json!(modules.len()));
    let first = parts
        .iter()
        .find_map(|(_, frame)| frame.get("topology").and_then(Value::as_object));
    let [edges, component_edges, requires, layers, mut gaps] = lists;
    let component_edges = merge_edges(component_edges);
    totals.insert("component_edges".to_owned(), json!(component_edges.len()));
    // The largest evidence list of one edge, as the projection of one scan counts it.
    let evidence_per_edge = edges
        .iter()
        .chain(&component_edges)
        .filter_map(|edge| edge["evidence_total"].as_u64())
        .max()
        .unwrap_or(0);
    totals.insert("evidence_per_edge".to_owned(), json!(evidence_per_edge));
    truncated |= evidence_per_edge > MAX_EVIDENCE as u64;
    complete &= !truncated;
    // The scope of the system is open: the topology names that reason as a gap (the shell reads
    // an open scope only with its reason among the gaps).
    if let Some(reason) = open.filter(|reason| !gaps.iter().any(|gap| gap == reason)) {
        gaps.push(json!(reason));
        complete = false;
    }
    Ok(Some(json!({
        "version": 1, "complete": complete, "truncated": truncated, "gaps": gaps,
        "budgets": first.and_then(|t| t.get("budgets")).cloned().unwrap_or(Value::Null),
        "total": totals, "components": components, "modules": modules, "edges": edges,
        "component_edges": component_edges, "requires": requires, "layers": layers,
    })))
}

/// The explanation of the system: the maps of each part by rule id, the held gaps in all.
pub(crate) fn explain(frames: &[Map<String, Value>]) -> Option<Value> {
    let mut parts = frames
        .iter()
        .filter_map(|frame| frame.get("explain").and_then(Value::as_object));
    let first = parts.next()?;
    let mut joined = first.clone();
    let mut all: Vec<&Map<String, Value>> = vec![first];
    all.extend(parts);
    let merge = |path: &[&str]| -> Map<String, Value> {
        all.iter()
            .filter_map(|e| {
                path.iter()
                    .try_fold(&Value::Object((*e).clone()), |v, k| v.get(k))
                    .cloned()
            })
            .filter_map(|v| v.as_object().cloned())
            .flatten()
            .collect()
    };
    joined.insert("rules".to_owned(), Value::Object(merge(&["rules"])));
    joined.insert("cycles".to_owned(), Value::Object(merge(&["cycles"])));
    // Each key of `holds` joins by its kind: a map by rule id, a list in order, a count as a sum,
    // and a flag as `or` (a truncated part makes the system truncated).
    let mut holds = Map::new();
    for part in all
        .iter()
        .filter_map(|e| e.get("holds").and_then(Value::as_object))
    {
        for (key, value) in part {
            match (holds.get_mut(key), value) {
                (None, _) => {
                    holds.insert(key.clone(), value.clone());
                }
                (Some(Value::Object(into)), Value::Object(more)) => into.extend(more.clone()),
                (Some(Value::Array(into)), Value::Array(more)) => into.extend(more.clone()),
                (Some(Value::Bool(into)), Value::Bool(more)) => *into |= more,
                (Some(into), Value::Number(more)) => {
                    let sum = into.as_u64().unwrap_or(0) + more.as_u64().unwrap_or(0);
                    *into = json!(sum);
                }
                _ => {}
            }
        }
    }
    // The list of the gaps that hold a rule keeps the budget of one part: the parts together may
    // hold more, and the frame states the cut (`gaps_truncated`) with the count that holds.
    let budget = joined
        .get("budgets")
        .and_then(|b| b.get("gaps"))
        .and_then(Value::as_u64)
        .and_then(|n| usize::try_from(n).ok());
    if let (Some(budget), Some(Value::Array(listed))) = (budget, holds.get_mut("gaps")) {
        listed.truncate(budget);
        let holding = holds
            .get("gaps_holding")
            .and_then(Value::as_u64)
            .unwrap_or(0);
        holds.insert("gaps_truncated".to_owned(), json!(holding > budget as u64));
    }
    joined.insert("holds".to_owned(), Value::Object(holds));
    Some(Value::Object(joined))
}

#[cfg(test)]
#[path = "system_topology_tests.rs"]
mod tests;
