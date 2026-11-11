// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One change between two contract revisions, and the two comparisons that every classifier
//! shares (Python `ir/widening_change.py`).

use std::collections::BTreeSet;

use serde_json::{Map, Value};

use crate::policy::pyrepr;
use crate::policy::reference::python_repr;

/// Whether a change permits more (widened) or less (narrowed). A widened change needs an
/// amendment.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChangeDirection {
    Widened,
    Narrowed,
}

/// What a change does to its field. Each kind is one family of Python messages.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChangeKind {
    /// A component, rule, budget or compatibility module is added or removed.
    Presence,
    /// A set field has a new entry.
    Gained,
    /// A set field lost an entry.
    Lost,
    /// A field has another value.
    Changed,
    /// A rule stops to cover imports for type checking only.
    Relaxed,
    /// A selector match changed from prefix to exact.
    MatchNarrowed,
    /// A forbidden dependency now permits an absent import namespace.
    AbsentNamespace,
    /// A cycle rule is limited to some components.
    Scoped,
    /// A ceiling or a threshold permits more.
    Raised,
    /// A compatibility module became permanent.
    Permanent,
    /// A rule kept its ID and changed its kind.
    KindChanged,
    /// A difference that no classifier names (fail closed).
    NotEnumerated,
    /// A `requires` entry is gone, or replaced by an entry that it contains.
    RequiresDropped,
}

record!(
    pub(crate),
    /// One change, with the subject, field and message of Python `WideningChange`.
    ContractChange {
        #[serde(skip)]
        direction: ChangeDirection,
        #[serde(skip)]
        kind: ChangeKind,
        subject: String,
        field: String,
        message: String,
    }
);

impl ContractChange {
    pub(crate) fn widened(kind: ChangeKind, subject: &str, field: &str, message: String) -> Self {
        ContractChange {
            direction: ChangeDirection::Widened,
            kind,
            subject: subject.to_owned(),
            field: field.to_owned(),
            message,
        }
    }

    pub(crate) fn narrowed(kind: ChangeKind, subject: &str, field: &str, message: String) -> Self {
        ContractChange {
            direction: ChangeDirection::Narrowed,
            ..ContractChange::widened(kind, subject, field, message)
        }
    }

    /// The change inside the scope of a mounted contract (`_inside_declaration_widenings`).
    pub(crate) fn inside(mut self, scope: &str) -> Self {
        let scope = python_repr(scope);
        self.subject = format!("inside {scope}.{}", self.subject);
        self.message = format!("inside {scope}: {}", self.message);
        self
    }
}

/// Sort as Python `sorted(findings, key=message)`; the sort is stable.
pub(crate) fn by_message(mut changes: Vec<ContractChange>) -> Vec<ContractChange> {
    changes.sort_by(|left, right| left.message.cmp(&right.message));
    changes
}

/// Python `set_widenings`: the entries that widen a set field, in sorted order.
pub(crate) fn set_widenings<'a>(
    subject: &str,
    field: &str,
    before: impl IntoIterator<Item = &'a str>,
    after: impl IntoIterator<Item = &'a str>,
    grows_widens: bool,
) -> Vec<ContractChange> {
    let before: BTreeSet<&str> = before.into_iter().collect();
    let after: BTreeSet<&str> = after.into_iter().collect();
    let (kind, verb, items) = if grows_widens {
        (ChangeKind::Gained, "gained", after.difference(&before))
    } else {
        (ChangeKind::Lost, "lost", before.difference(&after))
    };
    items
        .map(|item| {
            let message = format!("{subject}.{field} {verb} {}", python_repr(item));
            ContractChange::widened(kind, subject, field, message)
        })
        .collect()
}

/// The fields that no classifier compares: Python `_ALWAYS_NEUTRAL`.
const NEUTRAL: [&str; 4] = ["id", "kind", "rationale", "provenance"];

/// Python `generic_field_widenings`: fail closed. Each field that is not neutral and not
/// `handled` widens when its value differs. The values are the canonical values of the fields;
/// an absent field is `None`, as in Python.
pub(crate) fn generic_widenings(
    subject: &str,
    before: Option<&Map<String, Value>>,
    after: Option<&Map<String, Value>>,
    handled: &[&str],
) -> Vec<ContractChange> {
    // Fail closed: a value without its fields cannot be shown to be equal, so it widens.
    let (Some(before), Some(after)) = (before, after) else {
        let message = format!("{subject} could not be compared field by field");
        return vec![ContractChange::widened(
            ChangeKind::NotEnumerated,
            subject,
            "fields",
            message,
        )];
    };
    let names: BTreeSet<&String> = before.keys().chain(after.keys()).collect();
    names
        .into_iter()
        .filter(|name| !NEUTRAL.contains(&name.as_str()) && !handled.contains(&name.as_str()))
        .filter(|name| absent_is_null(before.get(*name)) != absent_is_null(after.get(*name)))
        .map(|name| {
            let message = format!(
                "{subject}.{name} changed from {} to {}",
                pyrepr::value(name, before.get(name)),
                pyrepr::value(name, after.get(name))
            );
            ContractChange::widened(ChangeKind::Changed, subject, name, message)
        })
        .collect()
}

fn absent_is_null(value: Option<&Value>) -> Option<&Value> {
    value.filter(|item| !item.is_null())
}

/// The canonical fields of a value of this crate, or `None` when serde gives no object.
pub(crate) fn fields_of<T: serde::Serialize>(value: &T) -> Option<Map<String, Value>> {
    match serde_json::to_value(value) {
        Ok(Value::Object(map)) => Some(map),
        _ => None,
    }
}
