// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `declarations.premises` (contract 3.17.0, AD-764): the premises that the contract states and
//! that a rule may rest on.
//!
//! A premise is a claim about what the scan cannot see. The contract opts in to a premise by its
//! name, with a reason. A rule that rests on a declared premise never reads as a plain PASS: the
//! frame names the premise and the run reads "PASS under <premise>". This file only reads the
//! shape and the known names; the model decides where a premise applies.

use serde::Serialize;

use crate::error::{invalid, Parsed};
use crate::json::{Json, Object};
use crate::model::ItemId;
use crate::read::{declared_items, nonempty_field, record};
use crate::version::{supports, ContractVersion, Feature};

/// A premise that a contract can declare by name. A new premise is a new variant, with its word
/// here and the place that reads it in the model.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PremiseName {
    /// No code of the run changes a module of the standard library of the language (#1538).
    StandardLibraryUnchanged,
    /// The compiler type-reach facts of the pinned toolchain prove that no body can run an impl (AD-1047).
    RustTypeReach,
}

/// Each premise name, in the order of the frame.
pub const PREMISE_NAMES: [PremiseName; 2] = [
    PremiseName::StandardLibraryUnchanged,
    PremiseName::RustTypeReach,
];

/// The word of a premise in the contract and in the frame.
pub fn premise_word(name: PremiseName) -> &'static str {
    match name {
        PremiseName::StandardLibraryUnchanged => "standard_library_unchanged",
        PremiseName::RustTypeReach => "rust_type_reach",
    }
}

/// A premise in words, as "PASS under <words>" reads it.
pub fn assumption_words(name: PremiseName) -> &'static str {
    match name {
        PremiseName::StandardLibraryUnchanged => {
            "the premise that outside code leaves the standard library unchanged"
        }
        PremiseName::RustTypeReach => {
            "rust_type_reach: the compiler type reach of the pinned rustc holds: the facts are of these files, this cfg set, this Cargo.lock and this target, the workspace is the whole program, and the scanned repository is trusted to build"
        }
    }
}

fn premise_of(text: &str) -> Option<PremiseName> {
    PREMISE_NAMES
        .into_iter()
        .find(|name| premise_word(*name) == text)
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
    let Some(items) = declared_items(
        object,
        "premises",
        (version, Feature::Premises),
        "premise declarations require contract schema_version 3.17.0",
    )?
    else {
        return Ok(Vec::new());
    };
    let found: Vec<DeclaredPremise> = items
        .iter()
        .enumerate()
        .map(|(index, raw)| {
            one(
                raw,
                version,
                &format!("contract.declarations.premises[{index}]"),
            )
        })
        .collect::<Parsed<_>>()?;
    let mut names: Vec<PremiseName> = Vec::new();
    for premise in &found {
        names.push(premise.name);
    }
    names.sort();
    let mut repeated = false;
    for pair in names.windows(2) {
        repeated |= pair[0] == pair[1];
    }
    if repeated {
        return Err(invalid("contract.declarations.premises repeats a name"));
    }
    Ok(found)
}

fn one(raw: &Json, version: ContractVersion, label: &str) -> Parsed<DeclaredPremise> {
    let (item, id, provenance) = record(raw, &["name", "rationale"], &[], label)?;
    let text: String = nonempty_field(item, "name", label)?;
    let known: Vec<&str> = PREMISE_NAMES.map(premise_word).to_vec();
    let Some(name) = premise_of(&text) else {
        return Err(invalid(format!(
            "{label}.name {text:?} names no premise that the core knows ({})",
            known.join(", ")
        )));
    };
    if name == PremiseName::RustTypeReach && !supports(version, Feature::RustTypeReach) {
        return Err(invalid(format!(
            "{label}.name rust_type_reach requires contract schema_version 3.21.0"
        )));
    }
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
