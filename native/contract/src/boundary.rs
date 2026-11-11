// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `boundary_types` with its allowed positions, and `protocol_declarations`.

use crate::error::{invalid, Parsed};
use crate::json::{field, has, Json, Object};
use crate::model_rules::{
    AliasBody, BoundaryAllowance, BoundaryTypes, ProtocolDeclarations, ProtocolSelector,
};
use crate::names::dotted_name;
use crate::read::{
    fields, flag, listed_sources, nonempty, nonempty_field, present, repeats, rule_record,
};
use crate::words::value_of;

pub(crate) fn boundary_types(raw: &Json, label: &str) -> Parsed<BoundaryTypes> {
    let (item, head) = rule_record(
        raw,
        &["source"],
        &["allowed_sources", "exact_sources", "allowed_positions"],
        label,
    )?;
    let (allowed_sources, exact_sources) = listed_sources(item, label)?;
    let entries = match field(item, "allowed_positions") {
        None => &[][..],
        Some(Json::Array(entries)) => entries.as_slice(),
        Some(_) => {
            return Err(invalid(format!(
                "{label}.allowed_positions must be an array"
            )))
        }
    };
    let allowed_positions = entries
        .iter()
        .enumerate()
        .map(|(index, entry)| allowance(entry, &format!("{label}.allowed_positions[{index}]")))
        .collect::<Parsed<Vec<_>>>()?;
    if repeats(&allowed_positions) {
        return Err(invalid(format!(
            "{label}.allowed_positions must contain unique entries"
        )));
    }
    Ok(BoundaryTypes {
        source: nonempty_field(item, "source", label)?,
        allowed_sources,
        exact_sources,
        allowed_positions,
        head,
    })
}

/// A depth: present, an integer of at least 1 that is not a Boolean.
fn depth(entry: &Object, key: &str, label: &str) -> Parsed<Option<u64>> {
    match field(entry, key) {
        None => Ok(None),
        Some(Json::Int(value)) if *value >= 1 => Ok(u64::try_from(*value).ok()),
        Some(_) => Err(invalid(format!("{label}.{key} must be a positive integer"))),
    }
}

fn alias_body(entry: &Object, key: &str, label: &str) -> Parsed<Option<AliasBody>> {
    let Some(raw) = field(entry, key) else {
        return Ok(None);
    };
    let body_label = format!("{label}.{key}");
    let body = fields(raw, &["origin", "shape"], &[], &body_label)?;
    Ok(Some(AliasBody {
        origin: nonempty_field(body, "origin", &body_label)?,
        shape: nonempty_field(body, "shape", &body_label)?,
    }))
}

const NATIVE_SHAPES: [&str; 3] = ["dict", "dict | None", "list[dict]"];
const BARE_MAPPINGS: [&str; 3] = ["Dict", "Mapping", "MutableMapping"];

/// `_parse_boundary_type_allowance`.
fn allowance(raw: &Json, label: &str) -> Parsed<BoundaryAllowance> {
    let entry = fields(
        raw,
        &["qualified_name", "position", "annotation"],
        &[
            "field_path",
            "container_depth",
            "mapping_depth",
            "alias_body",
            "key_alias_body",
            "literal_mapping_arm",
            "native_mapping",
        ],
        label,
    )?;
    let field_path = match field(entry, "field_path") {
        None => String::new(),
        Some(Json::Text(path)) if path.is_empty() => String::new(),
        Some(value) => nonempty(value, &format!("{label}.field_path"))?,
    };
    let annotation: String = nonempty_field(entry, "annotation", label)?;
    let container_depth = depth(entry, "container_depth", label)?;
    let mapping_depth = depth(entry, "mapping_depth", label)?;
    let routed = !field_path.is_empty();
    if let Some(levels) = mapping_depth {
        if routed {
            return Err(invalid(format!(
                "{label}.mapping_depth cannot select a DTO field"
            )));
        }
        if container_depth.is_some_and(|outer| Some(outer) != levels.checked_add(1)) {
            return Err(invalid(format!(
                "{label}.container_depth must be mapping_depth plus one"
            )));
        }
    }
    let alias = alias_body(entry, "alias_body", label)?;
    if alias.is_some() && (routed || mapping_depth.is_some()) {
        return Err(invalid(format!(
            "{label}.alias_body requires empty field_path"
        )));
    }
    let key_alias = alias_body(entry, "key_alias_body", label)?;
    if key_alias.is_some() && (routed || container_depth.is_some() || mapping_depth.is_some()) {
        return Err(invalid(format!(
            "{label}.key_alias_body requires empty field_path"
        )));
    }
    let arm = literal_arm(entry, routed, label)?;
    let native_mapping = native(entry, &annotation, label)?;
    if annotation == "dict" && !native_mapping {
        return Err(invalid(format!(
            "{label}.annotation cannot allow bare dict"
        )));
    }
    if !routed && BARE_MAPPINGS.contains(&annotation.as_str()) {
        return Err(invalid(format!(
            "{label}.annotation cannot allow a bare mapping"
        )));
    }
    Ok(BoundaryAllowance {
        qualified_name: nonempty_field(entry, "qualified_name", label)?,
        position: nonempty_field(entry, "position", label)?,
        field_path,
        annotation,
        container_depth,
        mapping_depth,
        alias_body: alias,
        key_alias_body: key_alias,
        literal_mapping_arm: arm,
        native_mapping,
    })
}

fn literal_arm(entry: &Object, routed: bool, label: &str) -> Parsed<Option<String>> {
    let Some(raw) = field(entry, "literal_mapping_arm") else {
        return Ok(None);
    };
    let arm = nonempty(raw, &format!("{label}.literal_mapping_arm"))?;
    let others = [
        "mapping_depth",
        "alias_body",
        "key_alias_body",
        "native_mapping",
    ];
    if routed || others.iter().any(|key| has(entry, key)) {
        return Err(invalid(format!(
            "{label}.literal_mapping_arm requires empty field_path and no other selectors"
        )));
    }
    Ok(Some(arm))
}

fn native(entry: &Object, annotation: &str, label: &str) -> Parsed<bool> {
    let Some(raw) = field(entry, "native_mapping") else {
        return Ok(false);
    };
    if !matches!(raw, Json::Bool(true)) {
        return Err(invalid(format!("{label}.native_mapping must be true")));
    }
    let others = [
        "container_depth",
        "mapping_depth",
        "alias_body",
        "key_alias_body",
        "literal_mapping_arm",
    ];
    if !NATIVE_SHAPES.contains(&annotation) || others.iter().any(|key| has(entry, key)) {
        return Err(invalid(format!(
            "{label}.native_mapping requires an exact bare dict shape only"
        )));
    }
    Ok(true)
}

/// `[A-Za-z_][A-Za-z0-9_]*`, one exact source identifier.
fn source_identifier(value: &str) -> bool {
    !value.contains('.') && dotted_name(value)
}

pub(crate) fn protocol_declarations(raw: &Json, label: &str) -> Parsed<ProtocolDeclarations> {
    let (item, head) = rule_record(raw, &["source", "protocol", "selectors"], &[], label)?;
    let source: String = nonempty_field(item, "source", label)?;
    let protocol: String = nonempty_field(item, "protocol", label)?;
    if !dotted_name(&source) {
        return Err(invalid(format!(
            "{label}.source must be a dotted source identity"
        )));
    }
    if !dotted_name(&protocol) || !protocol.contains('.') {
        return Err(invalid(format!(
            "{label}.protocol must be a canonical module.symbol"
        )));
    }
    let entries = match present(item, "selectors", label)? {
        Json::Array(entries) if !entries.is_empty() => entries,
        _ => {
            return Err(invalid(format!(
                "{label}.selectors must be a nonempty array"
            )))
        }
    };
    let mut selectors = Vec::new();
    for (index, raw_selector) in entries.iter().enumerate() {
        selectors.push(protocol_selector(
            raw_selector,
            &format!("{label}.selectors[{index}]"),
        )?);
    }
    let keys: Vec<_> = selectors
        .iter()
        .map(|selector| (selector.role, selector.name.clone()))
        .collect();
    if repeats(&keys) {
        return Err(invalid(format!(
            "{label}.selectors must not repeat a role and name"
        )));
    }
    Ok(ProtocolDeclarations {
        source: crate::model::Selector(source),
        protocol: crate::model::Selector(protocol),
        selectors,
        head,
    })
}

fn protocol_selector(raw: &Json, label: &str) -> Parsed<ProtocolSelector> {
    let selector = fields(raw, &["role", "name", "visibility"], &["optional"], label)?;
    let unsupported = || invalid(format!("{label} has an unsupported role or visibility"));
    let role_text: String = nonempty_field(selector, "role", label)?;
    let visibility_text: String = nonempty_field(selector, "visibility", label)?;
    let role = value_of(&role_text).ok_or_else(unsupported)?;
    let visibility = value_of(&visibility_text).ok_or_else(unsupported)?;
    let optional = flag(selector, "optional", false, label)?;
    let name: String = nonempty_field(selector, "name", label)?;
    if !source_identifier(&name) {
        return Err(invalid(format!(
            "{label}.name must be one exact source identifier"
        )));
    }
    Ok(ProtocolSelector {
        role,
        name,
        visibility,
        optional,
    })
}
