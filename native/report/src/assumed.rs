// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The premises of a PASS: what the contract states and the facts do not prove (AD-664, AD-764).
//!
//! A premise (a declared door reach, a stated external user, a premise that the contract declares
//! by name) is a claim of the contract, not a proof. A PASS of a rule that rests on one is never a
//! plain PASS: the frame names each premise of the rule in `premises`, the door sites also in
//! `assumed` (AD-664), each applied door declaration in `door_reach`, and the premises of the run
//! in words in `assuming`. The text and the page print "PASS assuming <assuming>". The model
//! decides which premises a rule rests on (`archkeel_model::rule_premises`).

use std::collections::BTreeMap;

use archkeel_contract::head_of;
use archkeel_model::{Applied, Model, ModelTree, PremiseKind, UsedPremise};
use serde::Serialize;

/// One premise of a PASS rule as the frame writes it: its kind word and its subject.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Premise {
    /// `door_reach`, `external_user`, or the name of a declared premise (AD-764).
    kind: String,
    /// The site, the item or the scope that the premise covers.
    subject: String,
}

/// The premises on which the PASS of the rule `id` of `model` rests.
pub(crate) fn of(model: &Model, id: &str) -> Vec<Premise> {
    let mut found: Vec<Premise> = Vec::new();
    for rule in model.contract().rules() {
        if head_of(rule).id().as_text() != id {
            continue;
        }
        let used: Vec<UsedPremise> = archkeel_model::rule_premises(model, rule);
        for premise in used {
            found.push(Premise {
                kind: archkeel_model::kind_word(premise.kind).to_owned(),
                subject: premise.subject,
            });
        }
    }
    found
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
    /// Each PASS rule that rests on a premise of the contract, with each premise (AD-764): never
    /// a plain PASS.
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    premises: BTreeMap<String, Vec<Premise>>,
    /// The premises of the run in words: a PASS that rests on them reads "PASS assuming" and
    /// these words (AD-764).
    #[serde(skip_serializing_if = "Option::is_none")]
    assuming: Option<String>,
}

impl Premises {
    /// The premises of the PASS rules and the applied door declarations of the run.
    pub(crate) fn of(premises: BTreeMap<String, Vec<Premise>>, models: Option<&ModelTree>) -> Self {
        let door_reach = rows(models);
        let door = archkeel_model::kind_word(PremiseKind::DoorReach);
        let mut assumed: BTreeMap<String, Vec<String>> = BTreeMap::new();
        let mut pairs: Vec<(&str, &str)> = Vec::new();
        for (rule, found) in &premises {
            let found: &Vec<Premise> = found;
            pairs.extend(found.iter().map(|p| {
                let kind: &str = &p.kind;
                let subject: &str = &p.subject;
                (kind, subject)
            }));
            let sites: Vec<String> = found
                .iter()
                .filter(|p| p.kind == door)
                .map(|p| p.subject.clone())
                .collect();
            if let [_, ..] = sites.as_slice() {
                assumed.insert(rule.clone(), sites);
            }
        }
        // Each kind word comes from `PremiseKind::kind_word` in `of`, so it reads back.
        let assuming = words(door_reach.len(), pairs.into_iter()).unwrap_or_default();
        Premises {
            assumed,
            door_reach,
            premises,
            assuming,
        }
    }
}

/// The premises of a run in words (`archkeel_model::premise_words`) from the kind words and the
/// subjects of a frame, or an error for a kind word that names no premise.
pub fn words<'a>(
    doors: usize,
    pairs: impl Iterator<Item = (&'a str, &'a str)>,
) -> Result<Option<String>, String> {
    let used: Vec<(PremiseKind, &str)> = pairs
        .map(|(word, subject)| {
            archkeel_model::of_kind_word(word)
                .map(|kind| (kind, subject))
                .ok_or_else(|| format!("the frame names a premise of the kind {word}"))
        })
        .collect::<Result<_, _>>()?;
    Ok(archkeel_model::premise_words(doors, &used))
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
