// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed view of the frame that the page reads (AD-496). The page copies these fields and
//! decides nothing. A field that is absent or has another shape reads as empty: the page then
//! shows less, never a wrong claim.

use std::collections::BTreeMap;

use serde::de::DeserializeOwned;
use serde::Deserialize;
use serde_json::Value;

/// A row of the frame that the page reads: a struct of public fields that reads as empty.
macro_rules! row {
    ($vis:vis, $($name:ident { $($field:ident: $kind:ty),* $(,)? })*) => {$(
        #[derive(Clone, Debug, Default, Deserialize)]
        $vis struct $name { $($vis $field: $kind),* }
    )*};
}

row! {
    pub(super),
    Location { path: String, line: i64 }
    Detail { source: String, target: Option<String>, cause: String, evidence: Vec<String> }
    Component { id: String, name: String }
    Module { name: String, path: String, component: Option<String> }
    Edge { source: String, target: String, resolution: String, count: usize }
    Totals { components: usize, modules: usize, component_edges: usize }
    Topology { total: Totals, components: Vec<Component>, modules: Vec<Module>, component_edges: Vec<Edge> }
    Shape { direction: String, source: Vec<String>, target: Vec<String> }
    Step { from: String, to: String, from_component: Option<String>, to_component: Option<String>, evidence: Vec<String>, evidence_total: usize }
    CyclePath { members: Vec<String>, path: Vec<Step>, steps_total: usize, truncated: bool }
    Cycles { total: usize, items: Vec<CyclePath> }
    Explain { rules: BTreeMap<String, Shape>, cycles: BTreeMap<String, Cycles> }
}

/// The parts of the frame that the page shows.
#[derive(Clone, Debug, Default)]
pub(super) struct Frame {
    pub(super) status: String,
    pub(super) rules: BTreeMap<String, (String, String)>,
    pub(super) details: BTreeMap<String, Vec<Detail>>,
    pub(super) locations: BTreeMap<String, Location>,
    pub(super) topology: Option<Topology>,
    pub(super) explain: Explain,
    pub(super) head: String,
}

fn field<T: DeserializeOwned + Default>(frame: &Value, key: &str) -> T {
    serde_json::from_value(frame[key].clone()).unwrap_or_default()
}

impl Frame {
    pub(super) fn of(frame: &Value) -> Frame {
        let head = frame["self_test"]["collect"]["request"]["snapshot"]["git_head"]
            .as_str()
            .unwrap_or_default()
            .chars()
            .take(9)
            .collect();
        Frame {
            status: frame["status"].as_str().unwrap_or("unavailable").to_owned(),
            rules: field(frame, "rules"),
            details: field(frame, "details"),
            locations: field(frame, "locations"),
            topology: serde_json::from_value(frame["topology"].clone()).ok(),
            explain: field(frame, "explain"),
            head,
        }
    }

    /// The number of rules with this verdict word.
    pub(super) fn rules_with(&self, word: &str) -> usize {
        self.rules.values().filter(|row| row.1 == word).count()
    }

    /// The file and line of an evidence id, as `path:line`.
    pub(super) fn place(&self, evidence: &str) -> Option<String> {
        let at = self.locations.get(evidence)?;
        Some(if at.line > 0 {
            format!("{}:{}", at.path, at.line)
        } else {
            at.path.clone()
        })
    }
}
