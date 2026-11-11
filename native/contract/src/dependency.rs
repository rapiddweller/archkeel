// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The dependency rules: `forbidden_dependency` with its selector grammar (`ir/dependency.py`),
//! `allowed_dependency` and `external_dependency_scope`.

use serde::de::DeserializeOwned;

use crate::error::{invalid, Parsed};
use crate::json::{field, Json, Object};
use crate::model::{
    AllowedDependency, ExternalDependencyScope, ForbiddenDependency, Selector, SelectorMatch,
    TargetKind,
};
use crate::names::{has_text, package_identity, python_identifier};
use crate::read::{listed_strings, named_sources, nonempty_field, present, rule_record};
use crate::words::value_of;

pub(crate) fn forbidden_dependency(raw: &Json, label: &str) -> Parsed<ForbiddenDependency> {
    let (item, head) = rule_record(
        raw,
        &["source", "target", "include_type_checking"],
        &[
            "target_symbol",
            "allowed_sources",
            "source_match",
            "target_match",
            "target_kind",
        ],
        label,
    )?;
    let include_type_checking = match present(item, "include_type_checking", label)? {
        Json::Bool(value) => *value,
        _ => {
            return Err(invalid(format!(
                "{label}.include_type_checking must be a boolean"
            )))
        }
    };
    let target_symbol = target_symbol(item, label)?;
    let source = selector_name(item, "source", label)?;
    let target = selector_name(item, "target", label)?;
    let source_match = selector_word(item, "source_match", label)?;
    let target_match = selector_word(item, "target_match", label)?;
    let target_kind = selector_word(item, "target_kind", label)?;
    Ok(ForbiddenDependency {
        head,
        source: Selector(source),
        target: Selector(target),
        include_type_checking,
        target_symbol,
        allowed_sources: listed_strings(item, "allowed_sources", label)?,
        source_match: source_match.unwrap_or(SelectorMatch::Prefix),
        target_match: target_match.unwrap_or(SelectorMatch::Prefix),
        target_kind: target_kind.unwrap_or(TargetKind::Module),
    })
}

/// `target_symbol`: absent or `null` is none, any other value must be an identifier.
fn target_symbol(item: &Object, label: &str) -> Parsed<Option<String>> {
    match field(item, "target_symbol") {
        None | Some(Json::Null) => Ok(None),
        Some(Json::Text(symbol)) if python_identifier(symbol) => Ok(Some(symbol.clone())),
        Some(_) => Err(invalid(format!(
            "{label}.target_symbol must be an identifier"
        ))),
    }
}

/// `_selector_name`: a string with text.
fn selector_name(item: &Object, key: &str, label: &str) -> Parsed<String> {
    match present(item, key, label)? {
        Json::Text(value) if has_text(value) => Ok(value.clone()),
        Json::Text(_) => Err(invalid(format!("{label}.{key} must not be empty"))),
        _ => Err(invalid(format!("{label}.{key} must be a string"))),
    }
}

/// A selector word: `None` when absent; a present `null` or an unknown word is an error.
fn selector_word<T: DeserializeOwned>(item: &Object, key: &str, label: &str) -> Parsed<Option<T>> {
    let Some(raw) = field(item, key) else {
        return Ok(None);
    };
    let Json::Text(value) = raw else {
        return Err(invalid(format!("{label}.{key} must be a string")));
    };
    value_of(value)
        .map(Some)
        .ok_or_else(|| invalid(format!("{value:?} is not a valid {key}")))
}

pub(crate) fn allowed_dependency(raw: &Json, label: &str) -> Parsed<AllowedDependency> {
    let (item, head) = rule_record(raw, &["source", "target"], &[], label)?;
    Ok(AllowedDependency {
        source: nonempty_field(item, "source", label)?,
        target: nonempty_field(item, "target", label)?,
        head,
    })
}

pub(crate) fn external_dependency_scope(
    raw: &Json,
    label: &str,
) -> Parsed<ExternalDependencyScope> {
    let (item, head) = rule_record(
        raw,
        &["dependency"],
        &["allowed_sources", "exact_sources"],
        label,
    )?;
    let dependency: String = nonempty_field(item, "dependency", label)?;
    if !python_identifier(&dependency) && !package_identity(&dependency) {
        return Err(invalid(format!(
            "{label}.dependency must be an import name or package identity"
        )));
    }
    let (allowed_sources, exact_sources) = named_sources(item, label)?;
    Ok(ExternalDependencyScope {
        head,
        dependency: Selector(dependency),
        allowed_sources,
        exact_sources,
    })
}
