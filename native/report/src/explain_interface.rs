// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The pairs and the imports that hold a rule, as the `explain` part writes them: the origin of
//! each pair and the cause of each import of an interface rule (#2086, AD-1210). It decides nothing.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::vocab::RouteWithheld;
use archkeel_model::{AbsentSymbol, InterfaceGap, InterfaceHold, PairOrigin};

use super::limits::MAX_HELD;

/// The most places that one rule lists: the causes that hold the most imports.
const MAX_PLACES: usize = 10;

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
/// the cause that the collector states (#2086, AD-1210).
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
    let mut places: Vec<_> = hold.places().collect();
    places.sort_by_key(|(_, at, count)| (std::cmp::Reverse(*count), *at));
    let places = places.into_iter().take(MAX_PLACES).map(
        |(cause, at, count)| serde_json::json!({"class": cause.as_str(), "at": at, "count": count}),
    );
    serde_json::json!({
        "classes": classes.collect::<Vec<_>>(),
        "imports": imports.collect::<Vec<_>>(),
        "places": places.collect::<Vec<_>>(),
    })
}

/// The assessments of a UML target that the core cannot decide: the kinds, and each symbol that
/// the inventory lacks with its module and the cause that an import states for it (#2242).
pub(super) fn uml_value(
    count: usize,
    kinds: &[String],
    absent: &[AbsentSymbol],
) -> serde_json::Value {
    let class = |held: &AbsentSymbol| match (&held.module, &held.cause) {
        (None, _) => "no_module",
        (Some(_), None) => "no_cause_stated",
        (Some(_), Some((cause, _))) => cause.as_str(),
    };
    let mut classes: BTreeMap<&str, usize> = BTreeMap::new();
    for held in absent {
        *classes.entry(class(held)).or_default() += 1;
    }
    let absent_rows = absent.iter().map(|held| {
        let at = held.cause.as_ref().and_then(|(_, at)| at.as_ref());
        serde_json::json!({
            "symbol": held.symbol, "module": held.module, "class": class(held), "at": at,
        })
    });
    serde_json::json!({
        "count": count,
        "kinds": kinds,
        "classes": classes.into_iter().map(|(class, count)| {
            serde_json::json!({"class": class, "count": count})
        }).collect::<Vec<_>>(),
        "absent": absent_rows.collect::<Vec<_>>(),
    })
}
