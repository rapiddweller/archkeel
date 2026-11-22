// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `declarations.trojan_horse_reach` (contract 3.15.0, AD-664): the declared reach of one trojan horse site.
//!
//! A trojan horse is a site that can run code or load a module that the scan does not see. Without a
//! declaration its gap leaves the code of every module unknown (AD-564). A declaration names one
//! site and the modules that the trojan horse may load or change. The model matches it to the trojan horse that
//! the collector states and reports a declaration that matches no trojan horse or more than one. This
//! file only reads the shape; it does not know the forms of a trojan horse (the model reads the word).

use crate::error::{invalid, Parsed};
use crate::json::{field, Json, Object};
use crate::model::{ItemId, Package};
use crate::names::{dotted_name, public_entry, qualified_identifier};
use crate::read::{
    declared_items, listed_strings, nonempty_field, positive, present, record, text,
};
use crate::version::{ContractVersion, Feature};

record!(
    pub(crate),
    /// The declared reach of one trojan horse site.
    TrojanHorseReach {
        /// The id of the item, unique in the contract.
        id: ItemId,
        /// The module that holds the trojan horse.
        module: Package,
        /// The form of the trojan horse, as the collector words it (`eval`, `loader`, ...). A record
        /// names its site by this or by `name`, not by both; empty when `name` names it.
        #[serde(skip_serializing_if = "String::is_empty")]
        trojan_horse: String,
        /// The qualified name that the collector prints for the site (`pickle.load`,
        /// `__self__`). Contract 3.20.0 (AD-1052).
        #[serde(rename = "name", skip_serializing_if = "Option::is_none")]
        site_name: Option<String>,
        /// How many sites the module has with this name, line and scope; the declaration
        /// applies to all of them or to none. Contract 3.20.0.
        #[serde(rename = "count", skip_serializing_if = "Option::is_none")]
        site_count: Option<u64>,
        /// The line of the site, counted from 1.
        #[serde(skip_serializing_if = "Option::is_none")]
        line: Option<u64>,
        /// The dotted names of the classes and functions that hold the site; empty text is the
        /// module level.
        #[serde(skip_serializing_if = "Option::is_none")]
        scope: Option<String>,
        /// The module prefixes that the trojan horse may import.
        #[serde(skip_serializing_if = "Option::is_none")]
        loads: Option<Vec<Package>>,
        /// A bound from a scanned literal tuple, instead of explicit prefixes.
        #[serde(skip_serializing_if = "Option::is_none")]
        loads_from: Option<ConstantLoad>,
        /// The module prefixes whose names the trojan horse may change.
        changes: Vec<Package>,
        /// Why the reach holds.
        rationale: String,
        /// The module prefixes whose modules may reach the name that the site binds. Without it, a
        /// module that can reach the name refuses the declaration. Contract 3.20.0 (AD-1056).
        #[serde(skip_serializing_if = "Vec::is_empty")]
        covers: Vec<Package>,
        /// Where the item comes from.
        provenance: Vec<String>,
    }
);

record!(
    pub(crate),
    /// The source binding, template and exact call of a loader bound.
    ConstantLoad {
        /// The binding as `module:name`.
        constant: String,
        /// An absolute module template with one `{}` segment.
        template: String,
        /// The source text of the call at the declared line.
        call: String,
    }
);

const REQUIRED: [&str; 2] = ["module", "rationale"];
const OPTIONAL: [&str; 10] = [
    "covers",
    "trojan_horse",
    "door",
    "name",
    "count",
    "line",
    "scope",
    "changes",
    "loads",
    "loads_from",
];

/// The trojan horse reach records, or none for an absent key, and whether the contract uses the
/// deprecated spelling `door_reach` or `door` (one note names the new keys). Both spellings of the
/// key together are a contract problem. The new key reads from contract 3.15.0 on, so that the canonical bytes of an old contract read again (AD-1054).
pub(crate) fn trojan_horse_reach(
    object: &Object,
    version: ContractVersion,
) -> Parsed<(Vec<TrojanHorseReach>, bool)> {
    let (old, new) = (
        field(object, "door_reach"),
        field(object, "trojan_horse_reach"),
    );
    if old.is_some() && new.is_some() {
        return Err(invalid(
            "contract.declarations names both door_reach and trojan_horse_reach; keep trojan_horse_reach",
        ));
    }
    let (key, feature) = match old {
        Some(_) => ("door_reach", Feature::TrojanHorseReach),
        None => ("trojan_horse_reach", Feature::TrojanHorseReach),
    };
    let unsupported = if old.is_some() {
        "door_reach declarations require contract schema_version 3.15.0"
    } else {
        "trojan_horse_reach declarations require contract schema_version 3.15.0"
    };
    let Some(items) = declared_items(object, key, (version, feature), unsupported)? else {
        return Ok((Vec::new(), false));
    };
    let mut deprecated = old.is_some();
    let mut records = Vec::new();
    for (index, raw) in items.iter().enumerate() {
        let (record, used) = one(raw, &format!("{key}[{index}]"), version)?;
        deprecated |= used;
        records.push(record);
    }
    Ok((records, deprecated))
}

fn one(raw: &Json, label: &str, version: ContractVersion) -> Parsed<(TrojanHorseReach, bool)> {
    let (item, id, provenance) = record(raw, &REQUIRED, &OPTIONAL, label)?;
    let module: Package = nonempty_field(item, "module", label)?;
    if !dotted_name(module.as_text()) {
        return Err(invalid(format!(
            "{label}.module must be a dotted module name"
        )));
    }
    let (trojan_horse, name, count, alias) = site_key(item, label, version)?;
    let trojan_horse = trojan_horse.unwrap_or_default();
    let line = match field(item, "line") {
        None => None,
        Some(raw) => Some(positive(raw, &format!("{label}.line"))?),
    };
    let scope = match field(item, "scope") {
        None => None,
        Some(raw) => Some(scope_text(raw, &format!("{label}.scope"))?),
    };
    // A name alone could re-attach to another function that uses the same name (AD-1058).
    if line.is_none() && scope.is_none() {
        return Err(invalid(format!(
            "{label} must name the site by line or scope, also when it names it by name"
        )));
    }
    let loads_from = field(item, "loads_from")
        .map(|raw| constant(raw, label, version))
        .transpose()?;
    if loads_from.is_some() {
        if field(item, "loads").is_some() || line.is_none() {
            return Err(invalid(format!(
                "{label}.loads_from requires a line and cannot be used with loads"
            )));
        }
    } else {
        present(item, "loads", label)?;
    }
    let loads = field(item, "loads")
        .map(|_| prefixes(item, "loads", label))
        .transpose()?;
    let covers = match field(item, "covers") {
        Some(_) => prefixes(item, "covers", label)?,
        None => Vec::new(),
    };
    if !covers.is_empty() && !crate::version::supports(version, Feature::TrojanHorseName) {
        return Err(invalid(format!(
            "{label}.covers requires contract schema_version 3.20.0"
        )));
    }
    let changes = prefixes(item, "changes", label)?;
    let record = TrojanHorseReach {
        id,
        module,
        trojan_horse,
        site_name: name,
        site_count: count,
        line,
        scope,
        loads,
        loads_from,
        covers,
        changes,
        rationale: nonempty_field(item, "rationale", label)?,
        provenance,
    };
    Ok((record, alias))
}

/// The form, the name and the count of a record: one of form and name, and a count of 1 or more.
/// The form, the name, the count and whether the form uses the deprecated word `door`.
type SiteKey = (Option<String>, Option<String>, Option<u64>, bool);

fn site_key(item: &Object, label: &str, version: ContractVersion) -> Parsed<SiteKey> {
    let text_of = |key: &str| {
        let found = field(item, key).map(|_| nonempty_field::<String>(item, key, label));
        found.transpose()
    };
    let (new, old): (Option<String>, Option<String>) = (text_of("trojan_horse")?, text_of("door")?);
    if new.is_some() && old.is_some() {
        return Err(invalid(format!(
            "{label} has both door and trojan_horse; keep trojan_horse"
        )));
    }
    let alias = old.is_some();
    let trojan_horse = new.or(old);
    let name = text_of("name")?;
    let count = field(item, "count")
        .map(|raw| positive(raw, &format!("{label}.count")))
        .transpose()?;
    let named = name.is_some() || count.is_some();
    if named && !crate::version::supports(version, Feature::TrojanHorseName) {
        return Err(invalid(format!(
            "{label}.name and {label}.count require contract schema_version 3.20.0"
        )));
    }
    if trojan_horse.is_some() == name.is_some() {
        return Err(invalid(format!(
            "{label} must name its site by trojan_horse or by name"
        )));
    }
    Ok((trojan_horse, name, count, alias))
}

fn constant(raw: &Json, label: &str, version: ContractVersion) -> Parsed<ConstantLoad> {
    if !crate::version::supports(version, Feature::ConstantLoad) {
        return Err(invalid(
            "loads_from requires contract schema_version 3.18.0",
        ));
    }
    let label = format!("{label}.loads_from");
    let fields = crate::read::fields(raw, &["constant", "template", "call"], &[], &label)?;
    let constant: String = nonempty_field(fields, "constant", &label)?;
    let template: String = nonempty_field(fields, "template", &label)?;
    let call = nonempty_field(fields, "call", &label)?;
    if !public_entry(&constant)
        || template.split('.').filter(|part| *part == "{}").count() != 1
        || !dotted_name(&template.replacen("{}", "item", 1))
    {
        return Err(invalid(format!(
            "{label} needs module:name and a dotted template with one {{}} segment"
        )));
    }
    Ok(ConstantLoad {
        constant,
        template,
        call,
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
    let values: Vec<Package> = listed_strings(item, key, label)?;
    if values.iter().any(|value| !dotted_name(value.as_text())) {
        return Err(invalid(format!(
            "{label}.{key} must hold dotted module names"
        )));
    }
    Ok(values)
}

#[cfg(test)]
#[path = "trojan_horse_reach_tests.rs"]
mod tests;
