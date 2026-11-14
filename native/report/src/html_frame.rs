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

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Location {
    pub(super) path: String,
    pub(super) line: i64,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Detail {
    pub(super) source: String,
    pub(super) target: Option<String>,
    pub(super) cause: String,
    pub(super) evidence: Vec<String>,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Component {
    pub(super) id: String,
    pub(super) name: String,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Module {
    pub(super) name: String,
    pub(super) path: String,
    pub(super) component: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Edge {
    pub(super) source: String,
    pub(super) target: String,
    pub(super) resolution: String,
    pub(super) count: usize,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Totals {
    pub(super) components: usize,
    pub(super) modules: usize,
    pub(super) component_edges: usize,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Topology {
    pub(super) total: Totals,
    pub(super) components: Vec<Component>,
    pub(super) modules: Vec<Module>,
    pub(super) component_edges: Vec<Edge>,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Shape {
    pub(super) direction: String,
    pub(super) source: Vec<String>,
    pub(super) target: Vec<String>,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Step {
    pub(super) from: String,
    pub(super) to: String,
    pub(super) from_component: Option<String>,
    pub(super) to_component: Option<String>,
    pub(super) evidence: Vec<String>,
    pub(super) evidence_total: usize,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct CyclePath {
    pub(super) members: Vec<String>,
    pub(super) path: Vec<Step>,
    pub(super) steps_total: usize,
    pub(super) truncated: bool,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Cycles {
    pub(super) total: usize,
    pub(super) items: Vec<CyclePath>,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub(super) struct Explain {
    pub(super) rules: BTreeMap<String, Shape>,
    pub(super) cycles: BTreeMap<String, Cycles>,
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
