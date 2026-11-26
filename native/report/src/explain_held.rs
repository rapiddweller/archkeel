// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the reason of one rule says about the gaps that hold it, for the `explain` part (AD-564).

use std::collections::BTreeSet;

use archkeel_facts::data::RouteWithheld;
use archkeel_model::{
    Cause, HoldClass, Incomplete, InterfaceGap, InterfaceHold, PairOrigin, Reason,
};
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

/// What the reason of one rule says about the gaps that hold it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) struct Held {
    pub(super) cause: WhyUnknown,
    pub(super) kind: HoldKind,
    pub(super) pairs: Vec<(String, String, Option<PairOrigin>)>,
    /// The ids of the gaps that the reason itself names (AD-564).
    pub(super) ids: Vec<String>,
    pub(super) unnamed_imports: usize,
    pub(super) interface: Option<InterfaceHolds>,
    pub(super) imports_total: usize,
}

impl Held {
    /// The kind of hold that a reason states, with the pairs, the gap ids and the unnamed
    /// imports that it names.
    pub(super) fn of(reason: &Reason) -> Held {
        let mut held = Held {
            cause: WhyUnknown::of(reason),
            kind: HoldKind::Other,
            pairs: Vec::new(),
            ids: Vec::new(),
            unnamed_imports: 0,
            interface: None,
            imports_total: 0,
        };
        if let Reason::Interface(hold) = reason {
            held.kind = HoldKind::InterfaceImports;
            held.interface = Some(InterfaceHolds::of(hold));
            held.imports_total = hold.total();
        }
        if let Reason::Incomplete(incomplete) = reason {
            held.kind = match incomplete {
                Incomplete::CoverageGaps { .. } => HoldKind::CoverageGaps,
                Incomplete::UnknownImports(count) => {
                    held.unnamed_imports = *count;
                    HoldKind::UnknownImports
                }
                Incomplete::NoSourceFiles => HoldKind::NoSourceFiles,
            };
        }
        if let Reason::NotComplete(Cause::PairGaps(pairs)) = reason {
            held.kind = HoldKind::PairGaps;
            held.pairs = distinct(pairs.pairs(), pairs.origins());
        }
        if let Reason::NotComplete(Cause::AllowedPairGaps(pairs)) = reason {
            held.kind = HoldKind::AllowedPairGaps;
            held.pairs = distinct(pairs.pairs(), &[]);
        }
        if let Reason::NotComplete(Cause::ScopedGaps(scoped)) = reason {
            held.kind = HoldKind::ScopedGaps;
            held.ids = scoped.ids().to_vec();
        }
        held
    }
}

/// The pairs of the gap records, each once, in the order of their first record, with the origin
/// of that record when the rule states one.
fn distinct(
    records: &[(String, String)],
    origins: &[PairOrigin],
) -> Vec<(String, String, Option<PairOrigin>)> {
    let mut seen = BTreeSet::new();
    records
        .iter()
        .enumerate()
        .filter(|(_, pair)| seen.insert(*pair))
        .map(|(at, (source, target))| (source.clone(), target.clone(), origins.get(at).copied()))
        .collect()
}

/// The most imports that one rule lists.
const MAX_IMPORTS: usize = 20;

/// One held import.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct HeldImport {
    source: String,
    target: String,
    name: Option<String>,
    gap: InterfaceGap,
    class: HoldClass,
    /// The cause that the collector states; null when it states none.
    cause: Option<RouteWithheld>,
    evidence: Vec<String>,
}

/// The number of held imports of one gap and class.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
struct ClassCount {
    gap: InterfaceGap,
    class: HoldClass,
    count: usize,
}

/// What holds an `interface_boundary` rule: the count of each class and the first imports.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(super) struct InterfaceHolds {
    classes: Vec<ClassCount>,
    imports: Vec<HeldImport>,
}

impl InterfaceHolds {
    /// The projection of the hold of one rule.
    pub(super) fn of(hold: &InterfaceHold) -> InterfaceHolds {
        InterfaceHolds {
            classes: hold
                .classes()
                .map(|(gap, class, count)| ClassCount { gap, class, count })
                .collect(),
            imports: hold
                .imports()
                .iter()
                .take(MAX_IMPORTS)
                .map(|held| HeldImport {
                    source: held.source.clone(),
                    target: held.target.clone(),
                    name: held.name.clone(),
                    gap: held.gap,
                    class: HoldClass::of(held.cause.as_ref()),
                    cause: held.cause.clone(),
                    evidence: held.evidence.clone(),
                })
                .collect(),
        }
    }
}
