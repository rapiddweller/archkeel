// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Eight of the rule kinds that only the Python profile decides: symbol placement, source
//! ownership, call owner, bounded numeric operand, forbidden call argument, the two catalog rules
//! and the guarded effect.

use crate::error::{invalid, Parsed};
use crate::json::{field, Json, Object};
use crate::model::SelectorMatch;
use crate::model_rules::{
    BoundedNumericOperand, CallOwner, CatalogArgument, CatalogUse, Condition,
    ForbiddenCallArgument, ForbiddenEffectUnderCondition, OwnershipMode, OwnershipRole,
    SourceOwnership, SymbolPlacement,
};
use crate::names::python_identifier;
use crate::read::{
    count, fields, given, listed_sources, listed_strings, named_sources, nonempty_field,
    optional_nonempty, present, rule_record, strings_field, text,
};
use crate::words::value_of;

/// Each word of a string list as a closed value, or the error `message`.
fn words<T: serde::de::DeserializeOwned>(values: &[String], message: String) -> Parsed<Vec<T>> {
    values
        .iter()
        .map(|value| value_of(value))
        .collect::<Option<Vec<T>>>()
        .ok_or_else(|| invalid(message))
}

pub(crate) fn symbol_placement(raw: &Json, label: &str) -> Parsed<SymbolPlacement> {
    let (item, head) = rule_record(
        raw,
        &["source", "class_kinds"],
        &["allowed_sources", "exact_sources"],
        label,
    )?;
    let names: Vec<String> = strings_field(item, "class_kinds", label, true)?;
    let class_kinds = words(
        &names,
        format!("{label}.class_kinds contains an unsupported class kind"),
    )?;
    let (allowed_sources, exact_sources) = named_sources(item, label)?;
    Ok(SymbolPlacement {
        source: nonempty_field(item, "source", label)?,
        class_kinds,
        allowed_sources,
        exact_sources,
        head,
    })
}

/// `_qualified_names`: unique strings whose parts are Python identifiers.
fn qualified_names(item: &Object, key: &str, label: &str) -> Parsed<Vec<String>> {
    let values: Vec<String> = listed_strings(item, key, label)?;
    if values
        .iter()
        .any(|value| !value.split('.').all(python_identifier))
    {
        return Err(invalid(format!(
            "{label}.{key} must contain qualified identifiers"
        )));
    }
    Ok(values)
}

const SYMBOL_ROLES: [OwnershipRole; 5] = [
    OwnershipRole::Definition,
    OwnershipRole::Read,
    OwnershipRole::Write,
    OwnershipRole::Delete,
    OwnershipRole::ValueTransfer,
];
const PARAMETER_ROLES: [OwnershipRole; 2] =
    [OwnershipRole::ParameterDefault, OwnershipRole::Fallback];
const RETIRED_ROLES: [OwnershipRole; 4] = [
    OwnershipRole::Definition,
    OwnershipRole::Read,
    OwnershipRole::Write,
    OwnershipRole::Delete,
];

pub(crate) fn source_ownership(raw: &Json, label: &str) -> Parsed<SourceOwnership> {
    let (item, head) = rule_record(
        raw,
        &["source", "mode", "roles"],
        &["symbols", "parameters", "owner", "value_owner"],
        label,
    )?;
    let unsupported = format!("{label}.mode or roles contains an unsupported value");
    let mode_text = text(present(item, "mode", label)?, &format!("{label}.mode"))
        .map_err(|_| invalid(unsupported.clone()))?;
    let mode: OwnershipMode = value_of(mode_text).ok_or_else(|| invalid(unsupported.clone()))?;
    let role_names: Vec<String> =
        strings_field(item, "roles", label, true).map_err(|_| invalid(unsupported.clone()))?;
    let roles: Vec<OwnershipRole> = words(&role_names, unsupported)?;
    let symbols = qualified_names(item, "symbols", label)?;
    let parameters = qualified_names(item, "parameters", label)?;
    if parameters.iter().any(|parameter| {
        parameter
            .rsplit_once('.')
            .is_none_or(|(owner, _)| owner.is_empty())
    }) {
        return Err(invalid(format!(
            "{label}.parameters must name function.parameter"
        )));
    }
    let owner = optional_nonempty(item, "owner", label)?;
    let value_owner = optional_nonempty(item, "value_owner", label)?;
    let symbol_roles = roles.iter().any(|role| SYMBOL_ROLES.contains(role));
    let parameter_roles = roles.iter().any(|role| PARAMETER_ROLES.contains(role));
    if symbols.is_empty() == symbol_roles || parameters.is_empty() == parameter_roles {
        return Err(invalid(format!(
            "{label} selectors must match their selected roles"
        )));
    }
    let retired = mode == OwnershipMode::Retired;
    let outside = roles.iter().any(|role| !RETIRED_ROLES.contains(role));
    if retired && (outside || owner.is_some() || value_owner.is_some()) {
        return Err(invalid(format!(
            "{label}.retired cannot select owners, parameters, defaults, or fallbacks"
        )));
    }
    if !retired && (symbol_roles != owner.is_some() || parameter_roles != value_owner.is_some()) {
        return Err(invalid(format!(
            "{label}.confined needs the owner for every selected role"
        )));
    }
    Ok(SourceOwnership {
        source: nonempty_field(item, "source", label)?,
        mode,
        roles,
        symbols: crate::model::wrap_all(symbols),
        parameters: crate::model::wrap_all(parameters),
        owner,
        value_owner,
        head,
    })
}

pub(crate) fn call_owner(raw: &Json, label: &str) -> Parsed<CallOwner> {
    let (item, head) = rule_record(
        raw,
        &["source", "target"],
        &["allowed_sources", "exact_sources"],
        label,
    )?;
    let (allowed_sources, exact_sources) = listed_sources(item, label)?;
    Ok(CallOwner {
        source: nonempty_field(item, "source", label)?,
        target: nonempty_field(item, "target", label)?,
        allowed_sources,
        exact_sources,
        head,
    })
}

pub(crate) fn bounded_numeric_operand(raw: &Json, label: &str) -> Parsed<BoundedNumericOperand> {
    let (item, head) = rule_record(
        raw,
        &["source", "form", "terminal_suffix", "minimum_value"],
        &[],
        label,
    )?;
    let form_text = text(present(item, "form", label)?, &format!("{label}.form"))?;
    let form = value_of(form_text).ok_or_else(|| invalid(format!("{label}.form is invalid")))?;
    Ok(BoundedNumericOperand {
        minimum_value: count(
            present(item, "minimum_value", label)?,
            &format!("{label}.minimum_value"),
        )?,
        terminal_suffix: nonempty_field(item, "terminal_suffix", label)?,
        source: nonempty_field(item, "source", label)?,
        form,
        head,
    })
}

pub(crate) fn forbidden_call_argument(raw: &Json, label: &str) -> Parsed<ForbiddenCallArgument> {
    let (item, head) = rule_record(raw, &["source", "target", "parameter"], &[], label)?;
    Ok(ForbiddenCallArgument {
        source: nonempty_field(item, "source", label)?,
        target: nonempty_field(item, "target", label)?,
        parameter: nonempty_field(item, "parameter", label)?,
        head,
    })
}

/// `SelectorMatch(_string(item.get("source_match", PREFIX)))`: `null` is an error.
fn source_match(item: &Object, label: &str) -> Parsed<SelectorMatch> {
    let Some(raw) = field(item, "source_match") else {
        return Ok(SelectorMatch::Prefix);
    };
    let word = text(raw, &format!("{label}.source_match"))?;
    value_of(word).ok_or_else(|| invalid(format!("{word:?} is not a valid SelectorMatch")))
}

pub(crate) fn catalog_argument(raw: &Json, label: &str) -> Parsed<CatalogArgument> {
    let (item, head) = rule_record(
        raw,
        &["source", "target", "parameter", "catalog"],
        &["overlays", "source_match"],
        label,
    )?;
    Ok(CatalogArgument {
        source: nonempty_field(item, "source", label)?,
        target: nonempty_field(item, "target", label)?,
        parameter: nonempty_field(item, "parameter", label)?,
        catalog: nonempty_field(item, "catalog", label)?,
        overlays: listed_strings(item, "overlays", label)?,
        source_match: source_match(item, label)?,
        head,
    })
}

pub(crate) fn catalog_use(raw: &Json, label: &str) -> Parsed<CatalogUse> {
    let (item, head) = rule_record(
        raw,
        &["source", "catalog"],
        &["overlays", "member", "source_match", "target", "parameter"],
        label,
    )?;
    if given(item, "target").is_some() != given(item, "parameter").is_some() {
        return Err(invalid(format!(
            "{label}.target and {label}.parameter must be provided together"
        )));
    }
    Ok(CatalogUse {
        source: nonempty_field(item, "source", label)?,
        catalog: nonempty_field(item, "catalog", label)?,
        overlays: listed_strings(item, "overlays", label)?,
        member: optional_nonempty(item, "member", label)?,
        source_match: source_match(item, label)?,
        target: optional_nonempty(item, "target", label)?,
        parameter: optional_nonempty(item, "parameter", label)?,
        head,
    })
}

pub(crate) fn forbidden_effect_under_condition(
    raw: &Json,
    label: &str,
) -> Parsed<ForbiddenEffectUnderCondition> {
    let (item, head) = rule_record(raw, &["source", "target", "condition"], &[], label)?;
    let condition_label = format!("{label}.condition");
    let selector = fields(
        present(item, "condition", label)?,
        &["kind", "owner", "name"],
        &[],
        &condition_label,
    )?;
    let kind_text: String = nonempty_field(selector, "kind", &condition_label)?;
    let kind = value_of(&kind_text).ok_or_else(|| {
        invalid(format!(
            "{kind_text:?} is not a valid ConditionSelectorKind"
        ))
    })?;
    Ok(ForbiddenEffectUnderCondition {
        source: nonempty_field(item, "source", label)?,
        target: nonempty_field(item, "target", label)?,
        condition: Condition {
            kind,
            owner: nonempty_field(selector, "owner", &condition_label)?,
            name: nonempty_field(selector, "name", &condition_label)?,
        },
        head,
    })
}
