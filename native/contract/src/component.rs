// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One component and its `requires` entries (`_parse_component`, `parse_required_component`).

use crate::error::{invalid, Parsed};
use crate::json::{field, has, Json, Object};
use crate::model::{
    wrap_all, Component, ComponentLabel, ItemId, Lifecycle, Package, Requirement, Selector,
};
use crate::names::{dotted_name, public_entry};
use crate::read::{
    contract_strings, decided_by, fields, given, nonempty, nonempty_field, object,
    optional_nonempty, present, record, strings_field, text,
};
use crate::version::{supports, ContractVersion, Feature};
use crate::words::value_of;

const REQUIRED: [&str; 5] = [
    "label",
    "role",
    "packages",
    "responsibilities",
    "forbidden_responsibilities",
];
const OPTIONAL: [&str; 10] = [
    "capability_id",
    "decided_by",
    "inside",
    "planned",
    "public",
    "requires",
    "namespace",
    "exact_modules",
    "layer",
    "lifecycle",
];

pub(crate) fn parse_component(
    raw: &Json,
    label: &str,
    version: ContractVersion,
) -> Parsed<Component> {
    let raw_fields = object(raw, label)?;
    if has(raw_fields, "lifecycle") && !supports(version, Feature::PlannedComponentOwner) {
        return Err(invalid(format!(
            "{label}.lifecycle requires contract schema_version 2.4.0"
        )));
    }
    if has(raw_fields, "layer") && !supports(version, Feature::Layers) {
        return Err(invalid(format!(
            "{label}.layer requires contract schema_version 2.3.0"
        )));
    }
    let (item, id, provenance) = record(raw, &REQUIRED, &OPTIONAL, label)?;
    let role_text = text(present(item, "role", label)?, &format!("{label}.role"))?;
    let role = value_of(role_text).ok_or_else(|| invalid(format!("{label}.role is invalid")))?;
    let lifecycle = lifecycle(item, label)?;
    let public = public_entries(item, "public", label)?;
    let planned = public_entries(item, "planned", label)?;
    let planned_owner = lifecycle == Some(Lifecycle::Planned);
    if planned_owner && public.as_ref().is_some_and(|entries| !entries.is_empty()) {
        return Err(invalid(format!(
            "{label}.planned owner cannot claim a current public API"
        )));
    }
    let requires = requires(item, label)?;
    let (packages, exact_modules) = owned_names(item, label, planned_owner)?;
    let namespace: Option<Package> = optional_nonempty(item, "namespace", label)?;
    if let Some(name) = &namespace {
        if !dotted_name(&name.0) {
            return Err(invalid(format!(
                "{label}.namespace must be a dotted Python package"
            )));
        }
        if !packages.contains(name) {
            return Err(invalid(format!(
                "{label}.namespace must name one of {label}.packages"
            )));
        }
    }
    Ok(Component {
        id,
        label: ComponentLabel(nonempty_field(item, "label", label)?),
        role,
        packages,
        responsibilities: strings_field(item, "responsibilities", label, false)?,
        forbidden_responsibilities: strings_field(
            item,
            "forbidden_responsibilities",
            label,
            false,
        )?,
        provenance,
        capability_id: optional_nonempty(item, "capability_id", label)?.map(ItemId),
        requires,
        inside: optional_nonempty(item, "inside", label)?,
        public,
        planned,
        decided_by: optional_decided_by(item, label)?,
        namespace,
        exact_modules,
        layer: match field(item, "layer") {
            Some(value) => Some(nonempty(value, &format!("{label}.layer"))?),
            None => None,
        },
        lifecycle,
    })
}

fn lifecycle(item: &Object, label: &str) -> Parsed<Option<Lifecycle>> {
    let Some(raw) = field(item, "lifecycle") else {
        return Ok(None);
    };
    let value = text(raw, &format!("{label}.lifecycle"))?;
    value_of(value)
        .map(Some)
        .ok_or_else(|| invalid(format!("{value:?} is not a valid ComponentLifecycle")))
}

fn optional_decided_by(item: &Object, label: &str) -> Parsed<Option<crate::model::DecidedBy>> {
    given(item, "decided_by")
        .map(|value| decided_by(value, &format!("{label}.decided_by")))
        .transpose()
}

/// `_public_entries`: `None` when absent or `null`, else entries of the `pkg.module[:Name]` form.
fn public_entries(item: &Object, key: &str, label: &str) -> Parsed<Option<Vec<Selector>>> {
    let Some(raw) = given(item, key) else {
        return Ok(None);
    };
    let entries: Vec<String> = contract_strings(raw, &format!("{label}.{key}"), false)?;
    match entries.iter().position(|entry| !public_entry(entry)) {
        Some(index) => Err(invalid(format!(
            "{label}.{key}[{index}] must be pkg.module or pkg.module:Name"
        ))),
        None => Ok(Some(wrap_all(entries))),
    }
}

fn requires(item: &Object, label: &str) -> Parsed<Option<Vec<Requirement>>> {
    let entries = match given(item, "requires") {
        None => return Ok(None),
        Some(Json::Array(entries)) => entries,
        Some(_) => return Err(invalid(format!("{label}.requires must be a list"))),
    };
    entries
        .iter()
        .enumerate()
        .map(|(index, entry)| requirement(entry, &format!("{label}.requires[{index}]")))
        .collect::<Parsed<Vec<_>>>()
        .map(Some)
}

fn requirement(raw: &Json, label: &str) -> Parsed<Requirement> {
    let item = fields(
        raw,
        &["component", "rationale"],
        &["through", "decided_by"],
        label,
    )?;
    let through = match field(item, "through") {
        Some(value) => contract_strings(value, &format!("{label}.through"), false)?,
        None => Vec::new(),
    };
    Ok(Requirement {
        component: ComponentLabel(nonempty_field(item, "component", label)?),
        rationale: nonempty_field(item, "rationale", label)?,
        through,
        decided_by: optional_decided_by(item, label)?,
    })
}

/// `_component_names`: the packages and exact modules that the component owns.
fn owned_names(
    item: &Object,
    label: &str,
    planned_owner: bool,
) -> Parsed<(Vec<Package>, Vec<Package>)> {
    let packages: Vec<Package> = strings_field(item, "packages", label, false)?;
    let exact: Vec<String> = match field(item, "exact_modules") {
        Some(value) => contract_strings(value, &format!("{label}.exact_modules"), false)?,
        None => Vec::new(),
    };
    if exact.iter().any(|name| !dotted_name(name)) {
        return Err(invalid(format!(
            "{label}.exact_modules must contain dotted identifiers"
        )));
    }
    let owns = !packages.is_empty() || !exact.is_empty();
    if planned_owner && owns {
        return Err(invalid(format!(
            "{label} planned owner cannot claim package or exact-module ownership"
        )));
    }
    if !planned_owner && !owns {
        return Err(invalid(format!(
            "{label} must claim at least one package or exact module"
        )));
    }
    Ok((packages, wrap_all(exact)))
}
