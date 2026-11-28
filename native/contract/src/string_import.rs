// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `declarations.string_imports` (contract 3.22.0, AD-1440): a string import that the team checked.
//!
//! A call that imports a module by a fixed string (`importlib.import_module("app.x")`) is brittle code and a
//! violation of the built-in rule `STRING-IMPORT` in every contract. A record names one site by its
//! module, its line and its literal target (and a count, when two sites share a line). The model
//! matches it to the site that the collector states. A declared site reads "PASS under its premise".

use crate::error::{invalid, Parsed};
use crate::json::{field, Json, Object};
use crate::model::{ItemId, Package};
use crate::names::dotted_name;
use crate::read::{declared_items, nonempty_field, positive, present, record};
use crate::version::{ContractVersion, Feature};

record!(
    pub(crate),
    /// One string import that the team checked.
    StringImportSite {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The module that holds the call.
        module: Package,
        /// The line of the call, counted from 1.
        line: u64,
        /// The module that the call names by its string.
        target: Package,
        /// How many calls the module has on this line; the declaration applies to all of them or to
        /// none.
        #[serde(rename = "count", skip_serializing_if = "Option::is_none")]
        site_count: Option<u64>,
        /// Why the string import is accepted.
        rationale: String,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

const REQUIRED: [&str; 4] = ["module", "line", "target", "rationale"];
const OPTIONAL: [&str; 1] = ["count"];

/// The declared string imports, or none for an absent key.
pub(crate) fn string_imports(
    object: &Object,
    version: ContractVersion,
) -> Parsed<Vec<StringImportSite>> {
    let Some(items) = declared_items(
        object,
        "string_imports",
        (version, Feature::StringImports),
        "string_imports declarations require contract schema_version 3.22.0",
    )?
    else {
        return Ok(Vec::new());
    };
    items
        .iter()
        .enumerate()
        .map(|(index, raw)| one(raw, &format!("string_imports[{index}]")))
        .collect()
}

fn one(raw: &Json, label: &str) -> Parsed<StringImportSite> {
    let (item, id, provenance) = record(raw, &REQUIRED, &OPTIONAL, label)?;
    let module: Package = nonempty_field(item, "module", label)?;
    let target: Package = nonempty_field(item, "target", label)?;
    for (key, name) in [("module", &module), ("target", &target)] {
        if !dotted_name(name.as_text()) {
            return Err(invalid(format!(
                "{label}.{key} must be a dotted module name"
            )));
        }
    }
    let site_count = match field(item, "count") {
        None => None,
        Some(raw) => Some(positive(raw, &format!("{label}.count"))?),
    };
    Ok(StringImportSite {
        id,
        module,
        line: positive(present(item, "line", label)?, &format!("{label}.line"))?,
        target,
        site_count,
        rationale: nonempty_field(item, "rationale", label)?,
        provenance,
    })
}
