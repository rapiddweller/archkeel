// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The premises of a PASS: what the contract states and the facts do not prove (AD-664, #1549).
//!
//! A declared reach of a door (AD-664) and a stated external user of a public item (#1549) are
//! premises of the contract, not proofs. A PASS of a rule that rests on one is never a plain PASS:
//! the frame names each premise of the rule in `premises`, the door sites also in `assumed`, each
//! applied door declaration in `door_reach`, and the premises of the run in words in `assuming`.
//! The text and the page print "PASS assuming <assuming>" from that one field.

use std::collections::BTreeMap;

use archkeel_contract::{head_of, Rule};
use archkeel_model::{Applied, Model, ModelTree};
use serde::Serialize;

/// What one premise is.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub(crate) enum PremiseKind {
    /// The declared reach of a door site (AD-664); the subject is the site.
    DoorReach,
    /// A stated user outside the scan of a public item (#1549); the subject is `module:name`.
    ExternalUser,
}

/// One premise of a PASS rule.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Premise {
    kind: PremiseKind,
    subject: String,
}

/// The premises on which the PASS of the rule `id` of `model` rests, in a fixed order: the door
/// sites, then the stated external users.
pub(crate) fn of(model: &Model, id: &str) -> Vec<Premise> {
    let Some(rule) = model
        .contract()
        .rules()
        .iter()
        .find(|rule| head_of(rule).id().as_text() == id)
    else {
        return Vec::new();
    };
    let doors = archkeel_model::assumed(model, rule)
        .into_iter()
        .map(|door| Premise {
            kind: PremiseKind::DoorReach,
            subject: door.site(),
        });
    let users = match rule {
        Rule::UnusedPublic(rule) => archkeel_model::stated_users(model, rule),
        _ => Vec::new(),
    };
    let users = users.into_iter().map(|item| Premise {
        kind: PremiseKind::ExternalUser,
        subject: format!("{}:{}", item.module, item.name),
    });
    doors.chain(users).collect()
}

/// The premises of a run as the frame writes them. The first two keys are the keys of AD-664.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Premises {
    /// Each PASS rule that holds only under the declared reach of door sites, with the sites
    /// (AD-664): never a plain PASS.
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    assumed: BTreeMap<String, Vec<String>>,
    /// Each applied declaration of a door reach of the run (AD-664).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    door_reach: Vec<DoorRow>,
    /// Each PASS rule that rests on a premise of the contract, with each premise (#1549): never a
    /// plain PASS.
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    premises: BTreeMap<String, Vec<Premise>>,
    /// The premises of the run in words: a PASS that rests on them reads "PASS assuming" and
    /// these words (#1549).
    #[serde(skip_serializing_if = "Option::is_none")]
    assuming: Option<String>,
}

impl Premises {
    /// The premises of the PASS rules and the applied door declarations of the run.
    pub(crate) fn of(premises: BTreeMap<String, Vec<Premise>>, models: Option<&ModelTree>) -> Self {
        let door_reach = rows(models);
        let assumed: BTreeMap<String, Vec<String>> = premises
            .iter()
            .map(|(rule, found)| {
                let sites = found.iter().filter(|p| p.kind == PremiseKind::DoorReach);
                (
                    rule.clone(),
                    sites.map(|p| p.subject.clone()).collect::<Vec<_>>(),
                )
            })
            .filter(|(_, sites)| !sites.is_empty())
            .collect();
        let users: std::collections::BTreeSet<&str> = premises
            .values()
            .flatten()
            .filter(|p| p.kind == PremiseKind::ExternalUser)
            .map(|p| p.subject.as_str())
            .collect();
        let assuming = words(door_reach.len(), users.len());
        Premises {
            assumed,
            door_reach,
            premises,
            assuming,
        }
    }
}

/// The premises of a run in words, or `None` without one: `the declared reach of N doors`,
/// `N stated external users`, or both joined by `and`. The one place of these words.
pub fn words(doors: usize, users: usize) -> Option<String> {
    let plural = |n: usize| if n == 1 { "" } else { "s" };
    let parts: Vec<String> = [
        (doors > 0).then(|| format!("the declared reach of {doors} door{}", plural(doors))),
        (users > 0).then(|| format!("{users} stated external user{}", plural(users))),
    ]
    .into_iter()
    .flatten()
    .collect();
    (!parts.is_empty()).then(|| parts.join(" and "))
}

/// One applied declaration as the frame writes it.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct DoorRow {
    /// The id of the declaration.
    id: String,
    /// The module of the door.
    module: String,
    /// The line of the door site.
    line: u32,
    /// The form of the door.
    door: &'static str,
    /// The declared module prefixes that the door may import.
    loads: Vec<String>,
    /// The declared module prefixes whose names the door may change.
    changes: Vec<String>,
}

/// The applied declarations of the run, in contract order; none without models.
fn rows(models: Option<&ModelTree>) -> Vec<DoorRow> {
    let applied = models.map(|models| models.root().graph().doors().applied());
    applied.into_iter().flatten().map(row).collect()
}

/// The row of one applied declaration.
fn row(door: &Applied) -> DoorRow {
    DoorRow {
        id: door.id.clone(),
        module: door.module.clone(),
        line: door.line,
        door: door.door(),
        loads: door.loads.clone(),
        changes: door.changes.clone(),
    }
}
