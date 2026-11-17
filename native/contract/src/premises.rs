// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `declarations.premises` (contract 3.17.0, AD-764): the premises that the contract states and
//! that a rule may rest on.
//!
//! A premise is a claim about what the scan cannot see. The contract opts in to a premise by its
//! name, with a reason. A rule that rests on a declared premise never reads as a plain PASS: the
//! frame names the premise and the run reads "PASS assuming <premise>". This file only reads the
//! shape and the known names; the model decides where a premise applies.

use serde::Serialize;

use crate::error::{invalid, Parsed};
use crate::json::{field, Json, Object};
use crate::model::ItemId;
use crate::read::{nonempty_field, record};
use crate::version::{supports, ContractVersion, Feature};

/// A premise that a contract can declare by name. A new premise is a new variant, with its word
/// here and the place that reads it in the model.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PremiseName {
    /// No code of the run changes a module of the standard library of the language (#1538).
    StandardLibraryUnchanged,
}

impl PremiseName {
    /// Each name, in the order of the frame.
    pub const ALL: [PremiseName; 1] = [PremiseName::StandardLibraryUnchanged];

    /// The word of the premise in the contract and in the frame.
    pub fn as_text(self) -> &'static str {
        match self {
            PremiseName::StandardLibraryUnchanged => "standard_library_unchanged",
        }
    }

    /// The premise in words, as "PASS assuming <words>" reads it.
    pub fn words(self) -> &'static str {
        match self {
            PremiseName::StandardLibraryUnchanged => "an unchanged standard library",
        }
    }

    fn of(text: &str) -> Option<PremiseName> {
        PremiseName::ALL
            .into_iter()
            .find(|name| name.as_text() == text)
    }
}

record!(
    pub(crate),
    /// One premise that the contract declares.
    DeclaredPremise {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The name of the premise.
        name: PremiseName,
        /// Why the premise holds for this project.
        rationale: String,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

/// The declared premises, or none for an absent key.
pub(crate) fn premises(object: &Object, version: ContractVersion) -> Parsed<Vec<DeclaredPremise>> {
    let items = match field(object, "premises") {
        None => return Ok(Vec::new()),
        Some(Json::Array(items)) => items,
        Some(_) => return Err(invalid("contract.declarations.premises must be an array")),
    };
    if !supports(version, Feature::Premises) {
        return Err(invalid(
            "premise declarations require contract schema_version 3.17.0",
        ));
    }
    let found: Vec<DeclaredPremise> = items
        .iter()
        .enumerate()
        .map(|(index, raw)| one(raw, &format!("contract.declarations.premises[{index}]")))
        .collect::<Parsed<_>>()?;
    let mut names: Vec<PremiseName> = found.iter().map(|p| p.name).collect();
    names.sort();
    if names.windows(2).any(|pair| pair[0] == pair[1]) {
        return Err(invalid("contract.declarations.premises repeats a name"));
    }
    Ok(found)
}

fn one(raw: &Json, label: &str) -> Parsed<DeclaredPremise> {
    let (item, id, provenance) = record(raw, &["name", "rationale"], &[], label)?;
    let text: String = nonempty_field(item, "name", label)?;
    let known: Vec<&str> = PremiseName::ALL.iter().map(|n| n.as_text()).collect();
    let Some(name) = PremiseName::of(&text) else {
        return Err(invalid(format!(
            "{label}.name {text:?} names no premise that the core knows ({})",
            known.join(", ")
        )));
    };
    Ok(DeclaredPremise {
        id,
        name,
        rationale: nonempty_field(item, "rationale", label)?,
        provenance,
    })
}

#[cfg(test)]
#[path = "premises_tests.rs"]
mod tests;
