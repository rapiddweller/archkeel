// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `forbidden_construct` rule with its allowed type ignores and its construct selector.

use crate::error::{invalid, Parsed};
use crate::json::{field, has, Json, Object};
use crate::model::{ConstructSelector, ForbiddenConstruct, Selector, SelectorRole, TypeIgnore};
use crate::names::{python_identifier, qualified_identifier};
use crate::read::{
    fields, listed_strings, nonempty, nonempty_field, positive, present, repeats, rule_record,
    strings_field,
};
use crate::words::value_of;

pub(crate) fn forbidden_construct(raw: &Json, label: &str) -> Parsed<ForbiddenConstruct> {
    let (item, head) = rule_record(
        raw,
        &["source", "constructs"],
        &[
            "allowed_sources",
            "exact_sources",
            "allowed_type_ignores",
            "selector",
        ],
        label,
    )?;
    let constructs = strings_field::<String>(item, "constructs", label, true)?
        .iter()
        .map(|name| value_of(name))
        .collect::<Option<Vec<_>>>()
        .ok_or_else(|| {
            invalid(format!(
                "{label}.constructs contains an unsupported construct"
            ))
        })?;
    let allowed_sources = listed_strings(item, "allowed_sources", label)?;
    let exact_sources = listed_strings(item, "exact_sources", label)?;
    let allowed_type_ignores = type_ignores(item, label)?;
    let selector = selector(item, label)?;
    let source = nonempty_field(item, "source", label)?;
    Ok(ForbiddenConstruct {
        head,
        source,
        constructs,
        allowed_sources,
        exact_sources,
        allowed_type_ignores,
        selector,
    })
}

fn type_ignores(item: &Object, label: &str) -> Parsed<Vec<TypeIgnore>> {
    let entries = match field(item, "allowed_type_ignores") {
        None => return Ok(Vec::new()),
        Some(Json::Array(entries)) => entries,
        Some(_) => {
            return Err(invalid(format!(
                "{label}.allowed_type_ignores must be an array"
            )))
        }
    };
    let mut ignores: Vec<TypeIgnore> = Vec::new();
    for (index, raw) in entries.iter().enumerate() {
        let entry_label = format!("{label}.allowed_type_ignores[{index}]");
        let entry = fields(
            raw,
            &["qualified_name", "line", "statement", "tag"],
            &[],
            &entry_label,
        )?;
        let line = positive(
            present(entry, "line", &entry_label)?,
            &format!("{entry_label}.line"),
        )?;
        ignores.push(TypeIgnore {
            qualified_name: nonempty_field(entry, "qualified_name", &entry_label)?,
            line,
            statement: nonempty_field(entry, "statement", &entry_label)?,
            tag: nonempty_field(entry, "tag", &entry_label)?,
        });
    }
    if repeats(&ignores) {
        return Err(invalid(format!(
            "{label}.allowed_type_ignores must contain unique entries"
        )));
    }
    Ok(ignores)
}

const ACCESS_ROLES: [SelectorRole; 3] =
    [SelectorRole::Read, SelectorRole::Write, SelectorRole::Call];
const MEMBERLESS_ROLES: [SelectorRole; 2] = [SelectorRole::Constructor, SelectorRole::TypeProbe];
const LITERAL_ROLES: [SelectorRole; 5] = [
    SelectorRole::Equality,
    SelectorRole::Membership,
    SelectorRole::Match,
    SelectorRole::Startswith,
    SelectorRole::Endswith,
];

/// `_parse_construct_selector`.
fn selector(item: &Object, label: &str) -> Parsed<Option<ConstructSelector>> {
    if !has(item, "selector") {
        return Ok(None);
    }
    let selector_label = format!("{label}.selector");
    let raw = present(item, "selector", label)?;
    let selected = fields(
        raw,
        &["receiver", "role"],
        &["member", "literal"],
        &selector_label,
    )?;
    let role_text: String = nonempty(
        present(selected, "role", &selector_label)?,
        &format!("{selector_label}.role"),
    )?;
    let role = value_of(&role_text)
        .ok_or_else(|| invalid(format!("{selector_label}.role is unsupported")))?;
    let receiver: Selector = nonempty_field(selected, "receiver", &selector_label)?;
    let member = match field(selected, "member") {
        None | Some(Json::Null) => None,
        Some(value) => Some(nonempty(value, &format!("{selector_label}.member"))?),
    };
    let literal = match field(selected, "literal") {
        None | Some(Json::Null) => None,
        Some(Json::Text(value)) => Some(value.clone()),
        Some(_) => {
            return Err(invalid(format!(
                "{selector_label}.literal must be a string"
            )))
        }
    };
    if ACCESS_ROLES.contains(&role) && literal.is_some() {
        return Err(invalid(format!(
            "{selector_label}.literal is not valid for access roles"
        )));
    }
    if MEMBERLESS_ROLES.contains(&role) == member.is_some() {
        return Err(invalid(format!(
            "{selector_label}.member is required for member roles"
        )));
    }
    if LITERAL_ROLES.contains(&role) != literal.is_some() {
        return Err(invalid(format!(
            "{selector_label}.literal is required only for operand roles"
        )));
    }
    let member_is_identifier = member.as_deref().is_none_or(python_identifier);
    if !qualified_identifier(&receiver.0) || !member_is_identifier {
        return Err(invalid(format!(
            "{selector_label} receiver and member must be qualified identifiers"
        )));
    }
    Ok(Some(ConstructSelector {
        receiver,
        member,
        role,
        literal,
    }))
}
