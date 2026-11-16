// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The architecture section (AD-606): one line of counts and the Explorer. The counts and the
//! Explorer read the same payload, so the line and the picture name the same components.

use serde_json::Value;

use super::atlas;
use super::cases::Names;
use super::explorer;
use super::frame::Frame;
use super::markup::{count, escape};
use super::places::{Kind, Places};

/// The components of the contract with a status, without the boxes of the layers and the groups.
fn components(payload: &Value) -> Vec<&Value> {
    payload["atlas"]["components"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|c| {
            !c["id"].as_str().is_some_and(|id| {
                ["LAYER:", "GROUP:", "PART:"]
                    .iter()
                    .any(|p| id.starts_with(p))
            })
        })
        .collect()
}

/// The violated places that name no module of a component.
fn outside(places: &Places, names: &Names<'_>) -> usize {
    places
        .every()
        .filter(|kind| match kind {
            Kind::Import { source, .. } => names.component(source).is_none(),
            Kind::Cycle(cycle) => cycle.members.iter().all(|m| names.component(m).is_none()),
        })
        .count()
}

pub(super) fn section(frame: &Frame, places: &Places, names: &Names<'_>) -> String {
    let Some(payload) = atlas::payload(frame, places, names) else {
        return String::new();
    };
    let all = components(&payload);
    let failing = all.iter().filter(|c| c["status"] == "FAIL").count();
    let unknown = all.iter().filter(|c| c["status"] == "UNKNOWN").count();
    let modules = payload["atlas"]["modules"].as_array().map_or(0, Vec::len);
    let lost = outside(places, names);
    let mut lede = format!(
        "{}, {}. {} with a violated place, {} with a gap.",
        count(all.len(), "component"),
        count(modules, "module"),
        failing,
        unknown
    );
    if let Some(note) = payload["atlas"]["language_note"].as_str() {
        lede.push(' ');
        lede.push_str(&escape(note));
    }
    if lost > 0 {
        lede.push_str(&format!(
            " {} in no component: assign the package of its module to a component of the contract, \
a root package too. See the violations below.",
            count(lost, "violated place")
        ));
        if places.total > places.shown.len() {
            lede.push_str(&format!(
                " <a href=\"#violations\">The list shows {} of {} violated places.</a>",
                places.shown.len(),
                places.total
            ));
        }
    }
    if !frame.named.is_empty() {
        lede.push_str(&format!(
            " {} of the run name no component: see Unknown.",
            count(frame.named.len(), "gap")
        ));
    }
    format!(
        "<section class=\"rp-sec\" aria-labelledby=\"arch\"><h2 class=\"h2\" id=\"arch\">Architecture</h2>\
<p class=\"body-sm rp-lede\">{lede} Open a box to see its parts; As-Is, Target and Diff switch the view.</p>\n{}</section>\n",
        explorer::section(&payload)
    )
}
