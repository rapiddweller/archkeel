// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The edge rows of the model, without the ranks (AD-372).
//!
//! A row of the `dependency_edges` section also holds `source_rank` and `target_rank`, which the
//! condensation of slice S3 gives. Until then the section is a named gap, and the frame carries
//! these rows in `edges`, so that the harness compares the edge lists with the reference engine
//! on every case. The rows are sorted by id, as the section is.

use archkeel_model::{reply_edges, Edge, Settings};
use archkeel_store::Ingested;
use serde_json::{json, Value};

/// The rows of the package and module edges of a reply, sorted by id. Settings that do not hold
/// for the reply give no rows; the rules of the frame name that refusal.
pub(crate) fn rows(reply: &Ingested, settings: &Settings) -> Option<Vec<Value>> {
    let mut edges = reply_edges(reply, settings).ok()?;
    edges.sort_by(|a, b| a.id().cmp(b.id()));
    Some(edges.iter().map(row).collect())
}

/// The 2.9 row of an edge (`aggregate_edges` in `check/evaluation/topology.py`), without ranks.
fn row(edge: &Edge) -> Value {
    let level = edge.level().name();
    let (source, target) = (edge.source(), edge.target());
    // `classified` drops an empty subject and sorts the others.
    let mut subjects: Vec<&str> = [source, target]
        .into_iter()
        .filter(|name| !name.is_empty())
        .collect();
    subjects.sort_unstable();
    json!({
        "id": edge.id(),
        "evidence_class": "FACT",
        "area": format!("{level}_topology"),
        "kind": format!("{level}_dependency"),
        "title": format!("{source} \u{2192} {target}"),
        "subjects": subjects,
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": edge.imports(),
        "provenance": [],
        "data": {
            "level": level,
            "source": source,
            "target": target,
            "count": edge.imports().len(),
            "type_checking_count": edge.type_checking(),
            "runtime_count": edge.runtime(),
            "bidirectional": edge.bidirectional(),
        },
    })
}
