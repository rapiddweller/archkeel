// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The output values of the `holds` part of the frame: the gaps that hold each rule, and for an
//! interface rule the held imports with the cause that the collector states (#2086, AD-1170).

use std::collections::BTreeMap;

use serde::Serialize;

use crate::why::WhyUnknown;

/// What kind of gap holds a rule.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub(super) enum HoldKind {
    CoverageGaps,
    PairGaps,
    AllowedPairGaps,
    /// Gaps that state their effect, and the rule reads the effect (AD-564).
    ScopedGaps,
    UnknownImports,
    /// The imports of an `interface_boundary` rule that it could not decide (`interface`).
    InterfaceImports,
    NoSourceFiles,
    /// Any other cause: the text of `explained` names it.
    Other,
}

/// The pair of a gap between two modules.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct Pair {
    pub(super) source: String,
    pub(super) target: String,
    /// Why the pair holds an interface rule; absent for the other rules.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) origin: Option<&'static str>,
}

/// The number of held pairs of one origin (an interface rule).
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct OriginCount {
    pub(super) origin: &'static str,
    pub(super) count: usize,
}

/// The gaps that hold one rule.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct RuleHolds {
    pub(super) cause: WhyUnknown,
    pub(super) kind: HoldKind,
    /// The ids of the coverage gaps of the reply that hold the rule.
    pub(super) gaps: Vec<String>,
    /// The first module pairs that hold the rule (a pair is two modules with a gap between them).
    pub(super) pairs: Vec<Pair>,
    /// The number of module pairs that hold the rule. A pair can have several gap records. A
    /// rule that no pair holds counts gap ids. `pairs` and `gaps` keep at most `held_per_rule`.
    pub(super) total: usize,
    /// True when `total` is larger than the lists that this frame keeps.
    pub(super) truncated: bool,
    /// The imports that the collector could not resolve and that no gap names.
    pub(super) unnamed_imports: usize,
    /// The number of held pairs of each origin, for an interface rule.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub(super) origins: Vec<OriginCount>,
    /// The held imports of an `interface_boundary` rule, each with its stated cause.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) interface: Option<InterfaceHolds>,
}

/// One coverage gap and the rules that it holds.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct GapHolds {
    pub(super) id: String,
    pub(super) kind: String,
    pub(super) reason: String,
    pub(super) rules: Vec<String>,
    pub(super) rules_total: usize,
    pub(super) truncated: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct Holds {
    pub(super) rules: BTreeMap<String, RuleHolds>,
    pub(super) gaps: Vec<GapHolds>,
    /// The number of coverage gaps of the reply.
    pub(super) gaps_total: usize,
    /// The number of coverage gaps that hold at least one rule.
    pub(super) gaps_holding: usize,
    pub(super) gaps_truncated: bool,
}

/// One held import.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct HeldImport {
    pub(super) source: String,
    pub(super) target: String,
    pub(super) name: Option<String>,
    pub(super) gap: &'static str,
    pub(super) class: &'static str,
    /// The cause that the collector states; null when it states none.
    pub(super) cause: Option<serde_json::Value>,
    pub(super) evidence: Vec<String>,
}

/// The number of held imports of one gap and class.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct ClassCount {
    pub(super) gap: &'static str,
    pub(super) class: &'static str,
    pub(super) count: usize,
}

/// What holds an `interface_boundary` rule: the count of each class and the first imports.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct InterfaceHolds {
    pub(super) classes: Vec<ClassCount>,
    pub(super) imports: Vec<HeldImport>,
}

/// One step of a cycle path.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct Step {
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub(super) possible: bool,
    pub(super) from: String,
    pub(super) to: String,
    pub(super) from_component: Option<String>,
    pub(super) to_component: Option<String>,
    pub(super) imports: usize,
    /// The declared edges of the step: the declaration, the module of its site and the module that
    /// it may load (AD-1057).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub(super) declared: Vec<DeclaredEdge>,
    pub(super) evidence: Vec<String>,
    pub(super) evidence_total: usize,
}

/// One possible import that a declaration supplies to a cycle step.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct DeclaredEdge {
    pub(super) declaration: String,
    pub(super) source: String,
    pub(super) target: String,
}

/// One cycle: its members and one closed path through them.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct CyclePath {
    pub(super) id: String,
    /// The position of the violation in `details` of the rule.
    pub(super) index: usize,
    pub(super) members: Vec<String>,
    pub(super) path: Vec<Step>,
    pub(super) steps_total: usize,
    pub(super) truncated: bool,
}

/// The cycles of one rule.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct Cycles {
    pub(super) total: usize,
    pub(super) truncated: bool,
    pub(super) items: Vec<CyclePath>,
}
