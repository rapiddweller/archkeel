// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The premises of a PASS: what the contract states and the facts do not prove (AD-664, AD-764).
//!
//! A premise (a declared trojan horse reach, a stated external user, a premise that the contract declares
//! by name) is a claim of the contract, not a proof. A PASS of a rule that rests on one is never a
//! plain PASS: the frame names each premise of the rule in `premises`, the trojan horse sites also in
//! `assumed` (AD-664), each applied trojan horse declaration in `trojan_horse_reach`, and the premises of the run
//! in words in `assuming`. The text and the page print "PASS under <assuming>". The model
//! decides which premises a rule rests on (`archkeel_model::rule_premises`).

use std::collections::BTreeMap;

use archkeel_contract::head_of;
use archkeel_model::{Applied, Model, ModelTree, PremiseKind, UsedPremise};
use serde::Serialize;

/// One premise of a PASS rule as the frame writes it: its kind word and its subject.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Premise {
    /// `trojan_horse_reach`, `external_user`, or the name of a declared premise (AD-764).
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

/// For each rule and each violation row of it, the (importer, imported) pairs that rest on a
/// declared possible import (`ViolationDetail::declared_pairs`).
pub(crate) type DeclaredPairs = BTreeMap<String, Vec<Vec<(String, String)>>>;

/// A note of the run: a fact that the reader must see and that changes no verdict (AD-1045).
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Note {
    /// The stable code of the note, such as `deprecated.trojan_horse_reach`.
    code: &'static str,
    /// The note in words.
    text: &'static str,
}

/// The note of a contract that spells its trojan horse keys with the deprecated word `door`.
const DEPRECATED_SPELLING: Note = Note {
    code: "deprecated.trojan_horse_reach",
    text: "The contract spells the key door_reach or the field door. Use trojan_horse_reach and \
           trojan_horse. The old spelling stops working at the next major version.",
};

/// The premises of a run as the frame writes them. The first two keys are the keys of AD-664.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct Premises {
    /// Each PASS rule that holds only under the declared reach of trojan horse sites, with the sites
    /// (AD-664): never a plain PASS.
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    assumed: BTreeMap<String, Vec<String>>,
    /// The notes of the run: facts that change no verdict (AD-1045).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    notes: Vec<Note>,
    /// Each applied declaration of a trojan horse reach of the run (AD-664).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    trojan_horse_reach: Vec<TrojanHorseRow>,
    /// Each FAIL rule whose every violation rests on an edge that a declaration only allows, with
    /// the ids of the declarations (AD-1043): the rule says "FAIL from a declared reach".
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    fail_from_declared_reach: BTreeMap<String, Vec<String>>,
    /// Each PASS rule that rests on a premise of the contract, with each premise (AD-764): never
    /// a plain PASS.
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    premises: BTreeMap<String, Vec<Premise>>,
    /// The premises of the run in words: a PASS that rests on them reads "PASS under" and
    /// these words (AD-764).
    #[serde(skip_serializing_if = "Option::is_none")]
    assuming: Option<String>,
}

impl Premises {
    /// The premises of the PASS rules and the applied trojan horse declarations of the run.
    pub(crate) fn of(
        premises: BTreeMap<String, Vec<Premise>>,
        models: Option<&ModelTree>,
        details: &DeclaredPairs,
    ) -> Self {
        let trojan_horse_reach = once(rows(models));
        let notes = notes_of(models);
        let fail_from_declared_reach = declared_fails(&trojan_horse_reach, details);
        let trojan_horse = archkeel_model::kind_word(PremiseKind::TrojanHorseReach);
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
                .filter(|p| p.kind == trojan_horse)
                .map(|p| p.subject.clone())
                .collect();
            if let [_, ..] = sites.as_slice() {
                assumed.insert(rule.clone(), sites);
            }
        }
        // Each kind word comes from `PremiseKind::kind_word` in `of`, so it reads back.
        let assuming = words(Vec::len(&trojan_horse_reach), pairs.into_iter()).unwrap_or_default();
        Premises {
            assumed,
            notes,
            trojan_horse_reach,
            fail_from_declared_reach,
            premises,
            assuming,
        }
    }
}

/// The premises of a run in words (`archkeel_model::premise_words`) from the kind words and the
/// subjects of a frame, or an error for a kind word that names no premise.
pub fn words<'a>(
    trojan_horses: usize,
    pairs: impl Iterator<Item = (&'a str, &'a str)>,
) -> Result<Option<String>, String> {
    let used: Vec<(PremiseKind, &str)> = pairs
        .map(|(word, subject)| {
            archkeel_model::of_kind_word(word)
                .map(|kind| (kind, subject))
                .ok_or_else(|| format!("the frame names a premise of the kind {word}"))
        })
        .collect::<Result<_, _>>()?;
    Ok(archkeel_model::premise_words(trojan_horses, &used))
}

/// One applied declaration as the frame writes it.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub(crate) struct TrojanHorseRow {
    /// The id of the declaration.
    id: String,
    /// Why the reach holds, as the declaration words it.
    rationale: String,
    /// The module of the trojan horse.
    module: String,
    /// The line of the trojan horse site.
    line: u32,
    /// The form of the trojan horse.
    trojan_horse: String,
    /// The declared module prefixes that the trojan horse may import.
    loads: Vec<String>,
    /// The scanned binding and template for a constant-bound premise.
    #[serde(skip_serializing_if = "Option::is_none")]
    constant: Option<String>,
    /// The scanned targets of the possible dependency edges, not observed imports.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    possible_loads: Vec<String>,
    /// The modules that can reach the bound name and that `covers` names (AD-1047).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    covered: Vec<String>,
    /// The declared module prefixes whose names the trojan horse may change.
    changes: Vec<String>,
}

/// The notes of the run: one for a contract that uses the deprecated word `door` (AD-1045).
fn notes_of(models: Option<&ModelTree>) -> Vec<Note> {
    if models.is_some_and(ModelTree::deprecated_spelling) {
        vec![DEPRECATED_SPELLING]
    } else {
        Vec::new()
    }
}

/// The applied declarations of the run, in contract order; none without models.
fn rows(models: Option<&ModelTree>) -> Vec<TrojanHorseRow> {
    let applied = models.map(|models| models.root().graph().trojan_horses().applied());
    applied.into_iter().flatten().map(row).collect()
}

/// One row for each declaration: a declaration with a `count` applies to several trojan horses.
fn once(all: Vec<TrojanHorseRow>) -> Vec<TrojanHorseRow> {
    let mut rows: Vec<TrojanHorseRow> = Vec::new();
    for next in all {
        if !rows.iter().any(|kept| kept.id == next.id) {
            rows.push(next);
        }
    }
    rows
}

/// The row of one applied declaration.
fn row(trojan_horse: &Applied) -> TrojanHorseRow {
    TrojanHorseRow {
        id: trojan_horse.id.clone(),
        rationale: trojan_horse.rationale.clone(),
        module: trojan_horse.module.clone(),
        line: trojan_horse.line,
        trojan_horse: trojan_horse.trojan_horse().to_owned(),
        loads: trojan_horse.loads.clone(),
        constant: trojan_horse.constant.clone(),
        possible_loads: trojan_horse
            .edges
            .iter()
            .map(|(target, _)| target.clone())
            .collect(),
        covered: trojan_horse.covered.clone(),
        changes: trojan_horse.changes.clone(),
    }
}

/// The FAIL rules whose every violation row rests on a declared possible import, with the ids of
/// the declarations that supply the edges (AD-1043).
fn declared_fails(
    trojan_horses: &[TrojanHorseRow],
    details: &DeclaredPairs,
) -> BTreeMap<String, Vec<String>> {
    let mut found: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (rule, rows) in details {
        let rows: &[Vec<(String, String)>] = rows;
        let every = !rows.is_empty() && rows.iter().all(|pairs| !Vec::is_empty(pairs));
        let mut ids: Vec<String> = Vec::new();
        for pair in rows.iter().flatten() {
            ids.extend(suppliers(trojan_horses, pair));
        }
        // A cycle names components, not modules: then every declaration with a load is a cause.
        if ids.is_empty() {
            ids.extend(
                trojan_horses
                    .iter()
                    .filter(|row| !Vec::is_empty(&row.possible_loads))
                    .map(|row| String::clone(&row.id)),
            );
        }
        ids.sort_unstable();
        ids.dedup();
        if every && !ids.is_empty() {
            found.insert(rule.clone(), ids);
        }
    }
    found
}

/// The ids of the declarations that allow the edge `pair` (importer, imported).
fn suppliers(trojan_horses: &[TrojanHorseRow], pair: &(String, String)) -> Vec<String> {
    let (source, target) = pair;
    let supplies = |trojan_horse: &&TrojanHorseRow| {
        let loads: &[String] = &trojan_horse.possible_loads;
        trojan_horse.module == *source && loads.iter().any(|name| name == target)
    };
    trojan_horses
        .iter()
        .filter(supplies)
        .map(|trojan_horse| String::clone(&trojan_horse.id))
        .collect()
}
