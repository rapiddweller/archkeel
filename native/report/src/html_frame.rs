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

use crate::head::{RuleVerdict, Status};

/// A row of the frame that the page reads: a struct of public fields that reads as empty.
macro_rules! row {
    ($vis:vis, $($name:ident { $($field:ident: $kind:ty),* $(,)? })*) => {$(
        #[derive(Clone, Debug, Default, Deserialize)]
        #[serde(default)]
        $vis struct $name { $($vis $field: $kind),* }
    )*};
}

row! {
    pub(super),
    Location { path: String, line: i64 }
    Detail { source: String, target: Option<String>, cause: String, evidence: Vec<String> }
    Component { id: String, name: String, parent: Option<String>, packages: Vec<String>, layer: Option<String>, public: Vec<String>, responsibilities: Vec<String>, forbidden_responsibilities: Vec<String>, planned_public: Vec<String>, provenance: Vec<String> }
    Module { name: String, path: String, component: Option<String>, language: String }
    Edge { source: String, target: String, resolution: String, count: usize, evidence: Vec<Location>, evidence_total: usize, rules: Vec<String> }
    Totals { components: usize, modules: usize, component_edges: usize, requires: usize, layers: usize }
    Require { source: String, target: String, imports: usize, rationale: String, through: Vec<String> }
    LayerOrder { rule: String, layers: Vec<String>, part: Option<String> }
    Topology { complete: bool, total: Totals, components: Vec<Component>, modules: Vec<Module>, edges: Vec<Edge>, component_edges: Vec<Edge>, requires: Vec<Require>, layers: Vec<LayerOrder> }
    Shape { direction: String, source: Vec<String>, target: Vec<String> }
    Step { from: String, to: String, from_component: Option<String>, to_component: Option<String>, evidence: Vec<String>, evidence_total: usize }
    CyclePath { index: usize, members: Vec<String>, path: Vec<Step>, steps_total: usize, truncated: bool }
    Cycles { total: usize, items: Vec<CyclePath> }
    Pair { source: String, target: String }
    RuleHolds { kind: String, pairs: Vec<Pair>, total: usize, unnamed_imports: usize }
    CollectionGap { kind: String, subjects: Vec<String>, reason: String, evidence: Vec<String>, detail: Option<String> }
    Holds { rules: BTreeMap<String, RuleHolds> }
    Interface { id: String, source: String, target: String, title: String, schema: String }
    Part { id: String, status: Option<Status>, rules: Vec<String> }
    Explain { rules: BTreeMap<String, Shape>, cycles: BTreeMap<String, Cycles>, holds: Holds }
}

/// What names the run: the snapshot, the bound contract and the core.
#[derive(Clone, Debug, Default)]
pub(super) struct Identity {
    pub(super) git_head: String,
    pub(super) contract_digest: String,
    pub(super) contract_files: BTreeMap<String, String>,
    pub(super) engine: String,
}

/// The rules of the run without a row, as `unsupported.rules` states them (AD-730, #1507).
#[derive(Clone, Debug, Default)]
pub(super) enum Unsupported {
    /// The frame states no list: it proves nothing about the rules without a row.
    #[default]
    Absent,
    /// Each rule or named gap without a row, with its reason. An empty list proves that each rule
    /// of the contract has a row.
    Each(BTreeMap<String, String>),
    /// One reason holds the whole contract.
    Whole,
}

/// The typed form of `unsupported.rules`.
fn rules_without_row(rules: &Value) -> Unsupported {
    match rules {
        Value::Object(_) => {
            serde_json::from_value(rules.clone()).map_or(Unsupported::Absent, Unsupported::Each)
        }
        Value::String(_) => Unsupported::Whole,
        _ => Unsupported::Absent,
    }
}

/// The system of the page of a part (E4): an input of the page that the frame does not carry.
#[derive(Clone, Debug, Deserialize)]
pub(super) struct PartOf {
    pub(super) system: String,
    pub(super) part: String,
    pub(super) href: Option<String>,
}

/// The parts of the frame that the page shows.
#[derive(Clone, Debug, Default)]
pub(super) struct Frame {
    /// The status of the run, or `None` when the frame states none (`unavailable`).
    pub(super) status: Option<Status>,
    /// Each rule row: its kind and its verdict.
    pub(super) rules: BTreeMap<String, (String, RuleVerdict)>,
    pub(super) details: BTreeMap<String, Vec<Detail>>,
    pub(super) locations: BTreeMap<String, Location>,
    pub(super) topology: Option<Topology>,
    /// What crosses between the parts of a system: a crossing that is no import.
    pub(super) interfaces: Vec<Interface>,
    /// The parts of a system, each with its own status and rules (AD-616).
    pub(super) parts: Vec<Part>,
    /// The title of the system of a system frame, empty for the run of one configuration.
    pub(super) system_title: String,
    /// The system that this page is a part of, when the request names one (E4).
    pub(super) part_of: Option<PartOf>,
    pub(super) explain: Explain,
    pub(super) head: String,
    pub(super) explained: BTreeMap<String, String>,
    /// The named gaps of the run that are no rule of the contract: an id and its reason.
    pub(super) named: BTreeMap<String, String>,
    /// The rules without a row, typed: the run-level floor reads it (AD-730, #1507).
    pub(super) unsupported: Unsupported,
    /// Whether the frame states its scope `complete`.
    pub(super) scope_complete: bool,
    pub(super) collection_gaps: Vec<CollectionGap>,
    /// The identity of the run: the digests of the contract, its files and the core.
    pub(super) identity: Identity,
    /// Why the run is not decided: the refusal or the scope text of the frame.
    pub(super) cause: String,
    /// The baseline of the request: its state and the number of accepted UNKNOWN entries (AD-546).
    pub(super) baseline: Option<(String, u64)>,
    /// The rule rows that the baseline accepts. Each stays UNKNOWN (AD-546).
    pub(super) accepted: std::collections::BTreeSet<String>,
    /// The assumption that the collector states for its proofs (AD-540), or empty.
    pub(super) premise: String,
    /// The call counts of the core (#1327), or `None` when it did not measure.
    pub(super) calls: Option<Calls>,
    /// Each PASS rule that holds only under declared door reaches, with the sites (AD-664).
    pub(super) assumed: BTreeMap<String, Vec<String>>,
    /// The number of applied door reach declarations of the run (AD-664).
    pub(super) doors: usize,
}

/// The call counts that the page shows: the classes of `Measures` of the model.
#[derive(Clone, Debug, Deserialize)]
pub(super) struct Calls {
    pub(super) calls_total: u64,
    pub(super) calls_resolved: u64,
    pub(super) calls_partial: u64,
    pub(super) calls_builtin: u64,
    pub(super) calls_external: u64,
    pub(super) calls_unresolved: u64,
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
        let text = |value: &Value| value.as_str().map(str::to_owned);
        let cause = text(&frame["self_test"]["collect"]["refused"])
            .or_else(|| text(&frame["unsupported"]["rules"]))
            .or_else(|| text(&frame["scope"]))
            .unwrap_or_default();
        let identity = Identity {
            git_head: frame["self_test"]["collect"]["request"]["snapshot"]["git_head"]
                .as_str()
                .unwrap_or_default()
                .to_owned(),
            contract_digest: text(&frame["contract_digest"]).unwrap_or_default(),
            contract_files: serde_json::from_value(
                frame["self_test"]["collect"]["contract_files"].clone(),
            )
            .unwrap_or_default(),
            engine: text(&frame["engine"])
                .unwrap_or_default()
                .trim_start_matches("archkeel-core ")
                .to_owned(),
        };
        Frame {
            identity,
            explained: field(frame, "explained"),
            collection_gaps: field(frame, "collection_gaps"),
            named: serde_json::from_value(frame["unsupported"]["rules"].clone())
                .unwrap_or_default(),
            unsupported: rules_without_row(&frame["unsupported"]["rules"]),
            scope_complete: frame["scope"].as_str() == Some("complete"),
            cause,
            premise: text(&frame["premise"]).unwrap_or_default(),
            calls: serde_json::from_value(frame["measures"].clone()).ok(),
            assumed: field(frame, "assumed"),
            doors: frame["door_reach"].as_array().map_or(0, Vec::len),
            status: serde_json::from_value(frame["status"].clone()).ok(),
            rules: field(frame, "rules"),
            details: field(frame, "details"),
            locations: field(frame, "locations"),
            topology: serde_json::from_value(frame["topology"].clone()).ok(),
            explain: field(frame, "explain"),
            interfaces: field(&frame["system"], "interfaces"),
            parts: field(&frame["system"], "parts"),
            system_title: frame["system"]["title"]
                .as_str()
                .unwrap_or_default()
                .to_owned(),
            part_of: serde_json::from_value(frame["part_of"].clone()).ok(),
            accepted: field(&frame["baseline"], "accepted_rules"),
            baseline: frame["baseline"]["state"].as_str().map(|state| {
                let accepted = frame["baseline"]["accepted_unknowns"].as_u64();
                (state.to_owned(), accepted.unwrap_or_default())
            }),
            head,
        }
    }

    /// The number of rules with this verdict.
    pub(super) fn rules_with(&self, verdict: RuleVerdict) -> usize {
        self.rules.values().filter(|row| row.1 == verdict).count()
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
