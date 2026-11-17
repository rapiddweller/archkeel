// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `declarations.door_reach` (contract 3.15.0, AD-664): the declared reach of one door site.
//!
//! A door is a site that can run code or load a module that the scan does not see. Without a
//! declaration its gap leaves the code of every module unknown (AD-564). A declaration names one
//! site and the modules that the door may load or change. The model matches it to the door that
//! the collector states and reports a declaration that matches no door or more than one. This
//! file only reads the shape; it does not know the forms of a door (the model reads the word).

use crate::error::{invalid, Parsed};
use crate::json::{field, Json, Object};
use crate::model::{ItemId, Package};
use crate::names::{dotted_name, qualified_identifier};
use crate::read::{
    declared_items, listed_strings, nonempty_field, positive, present, record, text,
};
use crate::version::{ContractVersion, Feature};

record!(
    pub(crate),
    /// The declared reach of one door site.
    DoorReach {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The module that holds the door.
        module: Package,
        /// The form of the door, as the collector words it (`eval`, `loader`, ...).
        door: String,
        /// The line of the site, counted from 1.
        #[serde(skip_serializing_if = "Option::is_none")]
        line: Option<u64>,
        /// The dotted names of the classes and functions that hold the site; empty text is the
        /// module level.
        #[serde(skip_serializing_if = "Option::is_none")]
        scope: Option<String>,
        /// The module prefixes that the door may import.
        loads: Vec<Package>,
        /// The module prefixes whose names the door may change.
        changes: Vec<Package>,
        /// Why the reach holds.
        rationale: String,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

const REQUIRED: [&str; 4] = ["module", "door", "loads", "rationale"];
const OPTIONAL: [&str; 3] = ["line", "scope", "changes"];

/// The door reach records, or none for an absent key.
pub(crate) fn door_reach(object: &Object, version: ContractVersion) -> Parsed<Vec<DoorReach>> {
    let Some(items) = declared_items(
        object,
        "door_reach",
        (version, Feature::DoorReach),
        "door_reach declarations require contract schema_version 3.15.0",
    )?
    else {
        return Ok(Vec::new());
    };
    items
        .iter()
        .enumerate()
        .map(|(index, raw)| one(raw, &format!("door_reach[{index}]")))
        .collect()
}

fn one(raw: &Json, label: &str) -> Parsed<DoorReach> {
    let (item, id, provenance) = record(raw, &REQUIRED, &OPTIONAL, label)?;
    let module: Package = nonempty_field(item, "module", label)?;
    if !dotted_name(module.as_text()) {
        return Err(invalid(format!(
            "{label}.module must be a dotted module name"
        )));
    }
    let door: String = nonempty_field(item, "door", label)?;
    let line = match field(item, "line") {
        None => None,
        Some(raw) => Some(positive(raw, &format!("{label}.line"))?),
    };
    let scope = match field(item, "scope") {
        None => None,
        Some(raw) => Some(scope_text(raw, &format!("{label}.scope"))?),
    };
    if line.is_none() && scope.is_none() {
        return Err(invalid(format!(
            "{label} must name the site by line or scope"
        )));
    }
    let loads = prefixes(item, "loads", label)?;
    let changes = prefixes(item, "changes", label)?;
    Ok(DoorReach {
        id,
        module,
        door,
        line,
        scope,
        loads,
        changes,
        rationale: nonempty_field(item, "rationale", label)?,
        provenance,
    })
}

/// The scope: empty text for the module level, else dotted identifiers.
fn scope_text(raw: &Json, label: &str) -> Parsed<String> {
    let value = text(raw, label)?;
    if value.is_empty() || qualified_identifier(value) {
        Ok(value.to_owned())
    } else {
        Err(invalid(format!(
            "{label} must be empty or dotted class and function names"
        )))
    }
}

/// A list of unique dotted module prefixes; an absent `changes` is empty.
fn prefixes(item: &Object, key: &str, label: &str) -> Parsed<Vec<Package>> {
    if key == "loads" {
        present(item, key, label)?;
    }
    let values: Vec<Package> = listed_strings(item, key, label)?;
    if values.iter().any(|value| !dotted_name(value.as_text())) {
        return Err(invalid(format!(
            "{label}.{key} must hold dotted module names"
        )));
    }
    Ok(values)
}

#[cfg(test)]
#[path = "door_reach_tests.rs"]
mod tests;
