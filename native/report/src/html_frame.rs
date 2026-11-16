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
        #[serde(default)]
        $vis struct $name { $($vis $field: $kind),* }
    )*};
}

row! {
    pub(super),
    Location { path: String, line: i64 }
    Detail { source: String, target: Option<String>, cause: String, evidence: Vec<String> }
    Component { id: String, name: String, parent: Option<String>, packages: Vec<String>, layer: Option<String>, public: Vec<String>, responsibilities: Vec<String>, forbidden_responsibilities: Vec<String>, planned_public: Vec<String> }
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

/// The parts of the frame that the page shows.
#[derive(Clone, Debug, Default)]
pub(super) struct Frame {
    pub(super) status: String,
    pub(super) rules: BTreeMap<String, (String, String)>,
    pub(super) details: BTreeMap<String, Vec<Detail>>,
    pub(super) locations: BTreeMap<String, Location>,
    pub(super) topology: Option<Topology>,
    /// What crosses between the parts of a system: a crossing that is no import.
    pub(super) interfaces: Vec<Interface>,
    pub(super) explain: Explain,
    pub(super) head: String,
    pub(super) explained: BTreeMap<String, String>,
    /// The named gaps of the run that are no rule of the contract: an id and its reason.
    pub(super) named: BTreeMap<String, String>,
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
            cause,
            premise: text(&frame["premise"]).unwrap_or_default(),
            calls: serde_json::from_value(frame["measures"].clone()).ok(),
            status: frame["status"].as_str().unwrap_or("unavailable").to_owned(),
            rules: field(frame, "rules"),
            details: field(frame, "details"),
            locations: field(frame, "locations"),
            topology: serde_json::from_value(frame["topology"].clone()).ok(),
            explain: field(frame, "explain"),
            interfaces: field(&frame["system"], "interfaces"),
            accepted: field(&frame["baseline"], "accepted_rules"),
            baseline: frame["baseline"]["state"].as_str().map(|state| {
                let accepted = frame["baseline"]["accepted_unknowns"].as_u64();
                (state.to_owned(), accepted.unwrap_or_default())
            }),
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
