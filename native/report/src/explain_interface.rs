// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The pairs and the imports that hold a rule, as the `explain` part writes them: the origin of
//! each pair and the cause of each import of an interface rule (#2086, AD-1170). It decides nothing.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::vocab::RouteWithheld;
use archkeel_model::{InterfaceGap, InterfaceHold, PairOrigin};

use super::limits::MAX_HELD;

/// The pairs of the gap records, each once, in the order of their first record, with the origin
/// of that record when the rule states one.
pub(super) fn distinct(
    records: &[(String, String)],
    origins: &[PairOrigin],
) -> Vec<(String, String, Option<PairOrigin>)> {
    let mut seen = BTreeSet::new();
    let each = records.iter().enumerate();
    each.filter(|(_, pair)| seen.insert(*pair))
        .map(|(at, (source, target))| (source.clone(), target.clone(), origins.get(at).copied()))
        .collect()
}

/// The number of pairs of each origin.
pub(super) fn origin_counts(
    pairs: &[(String, String, Option<PairOrigin>)],
) -> Vec<serde_json::Value> {
    let mut counts: BTreeMap<PairOrigin, usize> = BTreeMap::new();
    for origin in pairs.iter().filter_map(|(_, _, origin)| *origin) {
        *counts.entry(origin).or_default() += 1;
    }
    let json = |(origin, count): (PairOrigin, usize)| serde_json::json!({"origin": PairOrigin::word(origin), "count": count});
    counts.into_iter().map(json).collect()
}

/// The held imports of an interface rule: the count of each gap and class, and the first 20 with
/// the cause that the collector states (#2086, AD-1170).
pub(super) fn interface_value(hold: &InterfaceHold) -> serde_json::Value {
    let class = |cause: Option<&(RouteWithheld, Option<String>)>| {
        cause.map_or("not_stated", |(cause, _)| cause.as_str())
    };
    let classes = hold.classes().map(|(gap, cause, count)| {
        let class = cause.map_or("not_stated", RouteWithheld::as_str);
        serde_json::json!({"gap": InterfaceGap::word(gap), "class": class, "count": count})
    });
    let imports = hold.imports().iter().take(MAX_HELD).map(|held| {
        serde_json::json!({
            "source": held.source, "target": held.target, "name": held.name,
            "gap": InterfaceGap::word(held.gap), "class": class(held.cause.as_ref()),
            "cause": held.cause.as_ref().map(|(kind, at)| {
                serde_json::json!({"kind": kind.as_str(), "at": at})
            }),
            "evidence": held.evidence,
        })
    });
    serde_json::json!({"classes": classes.collect::<Vec<_>>(), "imports": imports.collect::<Vec<_>>()})
}
