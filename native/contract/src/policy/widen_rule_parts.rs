// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The parts that the rule classifiers of `widen_rules` share: the fail-closed field comparison
//! of a rule, the Python `repr` of nested values, and the classifiers of the cycle rule and of
//! the source lists.

use serde_json::{Map, Value};

use crate::model::CycleLevel;
use crate::model_rules::{AliasBody, BoundaryAllowance};
use crate::policy::change::{generic_widenings, set_widenings, ChangeKind, ContractChange};
use crate::policy::pyrepr::{list, texts, word};
use crate::policy::reference::python_repr;
use crate::rule::{body_of, head_of, Rule};

/// The canonical fields of a rule that Python `asdict` holds, without the head but with its
/// author.
pub(crate) fn rule_fields(rule: &Rule) -> Option<Map<String, Value>> {
    let Value::Object(mut fields) = body_of(rule) else {
        return None;
    };
    fields.remove("head");
    fields.insert(
        "decided_by".to_owned(),
        Value::String(word(&head_of(rule).decided_by)),
    );
    Some(fields)
}

pub(crate) fn generic(
    subject: &str,
    before: &Rule,
    after: &Rule,
    handled: &[&str],
) -> Vec<ContractChange> {
    generic_widenings(
        subject,
        rule_fields(before).as_ref(),
        rule_fields(after).as_ref(),
        handled,
    )
}

pub(crate) fn relaxed(subject: &str, before: bool, after: bool) -> Vec<ContractChange> {
    if !(before && !after) {
        return Vec::new();
    }
    let message = format!("{subject}.include_type_checking relaxed from true to false");
    vec![ContractChange::widened(
        ChangeKind::Relaxed,
        subject,
        "include_type_checking",
        message,
    )]
}

pub(crate) fn gained(subject: &str, field: &str, items: Vec<String>) -> Vec<ContractChange> {
    items
        .into_iter()
        .map(|item| {
            let message = format!("{subject}.{field} gained {item}");
            ContractChange::widened(ChangeKind::Gained, subject, field, message)
        })
        .collect()
}

/// The entries of `after` that `before` does not hold, without repeats, as Python sets do.
pub(crate) fn new_entries<'a, T: PartialEq>(before: &[T], after: &'a [T]) -> Vec<&'a T> {
    let mut found: Vec<&T> = Vec::new();
    for item in after {
        if !before.contains(item) && !found.contains(&item) {
            found.push(item);
        }
    }
    found
}

pub(crate) fn number(value: Option<u64>) -> String {
    value.map_or_else(|| "None".to_owned(), |item| item.to_string())
}

pub(crate) fn alias(value: Option<&AliasBody>) -> String {
    value.map_or_else(
        || "None".to_owned(),
        |body| {
            let (origin, shape) = (python_repr(&body.origin), python_repr(&body.shape));
            format!("BoundaryAliasBody(origin={origin}, shape={shape})")
        },
    )
}

/// Python `BoundaryTypeAllowance.__repr__`: an optional field only when it is set.
pub(crate) fn allowance(item: &BoundaryAllowance) -> String {
    let mut text = format!(
        "BoundaryTypeAllowance(qualified_name={}, position={}, field_path={}, annotation={}, \
         container_depth={}",
        python_repr(&item.qualified_name),
        python_repr(&item.position),
        python_repr(&item.field_path),
        python_repr(&item.annotation),
        number(item.container_depth),
    );
    if let Some(depth) = item.mapping_depth {
        text.push_str(&format!(", mapping_depth={depth}"));
    }
    if item.alias_body.is_some() {
        text.push_str(&format!(", alias_body={}", alias(item.alias_body.as_ref())));
    }
    if item.key_alias_body.is_some() {
        text.push_str(&format!(
            ", key_alias_body={}",
            alias(item.key_alias_body.as_ref())
        ));
    }
    if let Some(arm) = &item.literal_mapping_arm {
        text.push_str(&format!(", literal_mapping_arm={}", python_repr(arm)));
    }
    if item.native_mapping {
        text.push_str(", native_mapping=True");
    }
    text.push(')');
    text
}

pub(crate) fn sources(
    subject: &str,
    before: &Rule,
    after: &Rule,
    allowed: [&Vec<crate::model::Selector>; 2],
    exact: [&Vec<crate::model::Selector>; 2],
) -> Vec<ContractChange> {
    let mut changes = set_widenings(
        subject,
        "allowed_sources",
        texts(allowed[0]),
        texts(allowed[1]),
        true,
    );
    changes.extend(set_widenings(
        subject,
        "exact_sources",
        texts(exact[0]),
        texts(exact[1]),
        true,
    ));
    changes.extend(generic(
        subject,
        before,
        after,
        &["allowed_sources", "exact_sources"],
    ));
    changes
}

pub(crate) fn cycles(
    subject: &str,
    before: &Rule,
    after: &Rule,
    old: &crate::model::NoComponentCycles,
    new: &crate::model::NoComponentCycles,
) -> Vec<ContractChange> {
    let level = |value: CycleLevel| word(&value);
    let mut changes = Vec::new();
    if old.level != new.level {
        let message = format!(
            "{subject}.level changed from {} to {}",
            level(old.level),
            level(new.level)
        );
        changes.push(ContractChange::widened(
            ChangeKind::Changed,
            subject,
            "level",
            message,
        ));
    }
    match (&old.components, &new.components) {
        (_, None) => {}
        (None, Some(scope)) => {
            let mut names = texts(scope);
            names.sort_unstable();
            let message = format!("{subject}.components scoped to {}", list(names));
            changes.push(ContractChange::widened(
                ChangeKind::Scoped,
                subject,
                "components",
                message,
            ));
        }
        (Some(was), Some(now)) => {
            changes.extend(set_widenings(
                subject,
                "components",
                texts(was),
                texts(now),
                false,
            ));
        }
    }
    changes.extend(generic(subject, before, after, &["level", "components"]));
    changes
}
