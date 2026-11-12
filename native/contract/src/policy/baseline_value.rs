// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Typed baseline content and field validation (AD-386).

use std::fmt;

use crate::json::{field, keys, Json, Object};
use crate::model_declarations::BudgetName;

/// Refuse larger input before the JSON reader allocates a tree.
pub const MAX_BASELINE_BYTES: usize = 16 * 1024 * 1024;

record!(pub(crate),
    /// Sorted rule ids and subjects. Repeated members remain part of the identity.
    BaselineFingerprint { rules: Vec<String>, subjects: Vec<String> }
);

record!(pub(crate),
    /// Direction evidence, separate from the fingerprint.
    BaselineRole { source: String, target: String }
);

record!(pub(crate),
    /// One checked debt entry. Only the codec can make one.
    BaselineViolation { fingerprint: BaselineFingerprint, count: u64, roles: Vec<BaselineRole> }
);

closed_enum!(NameBudgetKind {
    FacadeNames,
    CouplingNames
});

/// A scalar or keyed budget. A keyed value is the length of its names, never another count.
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
pub enum BaselineBudget {
    Scalar {
        name: BudgetName,
        value: u64,
    },
    Names {
        kind: NameBudgetKind,
        key: String,
        names: Vec<String>,
    },
}

record!(pub(crate),
    /// Checked baseline content, sorted as Python sorts it. No rule or staleness check occurs.
    ValidationBaseline { violations: Vec<BaselineViolation>, budgets: Vec<BaselineBudget> }
);

/// A baseline validation failure. Labels are paths into the input, not unchecked field maps.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BaselineError {
    Json(String),
    DuplicateKey(String),
    TooLarge,
    IntegerRange(String),
    NotObject(String),
    UnsupportedSchema(String),
    FieldsMismatch(String),
    NotArray(String),
    NotString(String),
    NotStrings(String),
    NotCount(String),
    ZeroCount(String),
    Empty(String),
    RepeatedRole(String),
    RepeatedFingerprint {
        index: usize,
        first: usize,
        name: String,
    },
    UnsupportedBudget(String),
    UnsortedNames(String),
}

impl fmt::Display for BaselineError {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(text) | Self::DuplicateKey(text) => out.write_str(text),
            Self::TooLarge => write!(out, "baseline exceeds the {MAX_BASELINE_BYTES}-byte limit"),
            Self::IntegerRange(label) => write!(out, "{label} exceeds the unsigned 64-bit integer range"),
            Self::NotObject(label) => write!(out, "{label} must be an object"),
            Self::UnsupportedSchema(value) => write!(out, "baseline schema {value} cannot be read as 1.0.0, 1.1.0, 1.2.0, 1.3.0"),
            Self::FieldsMismatch(label) => write!(out, "{label} fields mismatch"),
            Self::NotArray(label) => write!(out, "{label} must be an array"),
            Self::NotString(label) => write!(out, "{label} must be a string"),
            Self::NotStrings(label) => write!(out, "{label} must be a string array"),
            Self::NotCount(label) => write!(out, "{label} must be a non-negative integer"),
            Self::ZeroCount(label) => write!(out, "{label} must be at least 1"),
            Self::Empty(label) => write!(out, "{label} must not be empty"),
            Self::RepeatedRole(label) => write!(out, "{label} repeats a role"),
            Self::RepeatedFingerprint { index, first, name } => write!(out, "baseline.violations[{index}] repeats baseline.violations[{first}], {name} (subjects match in any order); give it one count instead"),
            Self::UnsupportedBudget(label) => write!(out, "{label} is not a supported measurement budget"),
            Self::UnsortedNames(label) => write!(out, "{label} must list sorted unique names"),
        }
    }
}

impl std::error::Error for BaselineError {}

pub(super) fn object<'a>(raw: &'a Json, label: &str) -> Result<&'a Object, BaselineError> {
    match raw {
        Json::Object(value) => Ok(value),
        _ => Err(BaselineError::NotObject(label.into())),
    }
}

pub(super) fn exact(raw: &Object, wanted: &[&str], label: &str) -> Result<(), BaselineError> {
    let mut seen: Vec<&str> = keys(raw).collect();
    seen.sort_unstable();
    let mut wanted = wanted.to_vec();
    wanted.sort_unstable();
    if seen == wanted {
        Ok(())
    } else {
        Err(BaselineError::FieldsMismatch(label.into()))
    }
}

pub(super) fn required<'a>(raw: &'a Object, key: &str) -> &'a Json {
    field(raw, key).unwrap_or(&Json::Null)
}

pub(super) fn strings(raw: &Json, label: &str) -> Result<Vec<String>, BaselineError> {
    if let Json::Array(values) = raw {
        let result: Option<Vec<String>> = values
            .iter()
            .map(|item| match item {
                Json::Text(text) => Some(text.clone()),
                _ => None,
            })
            .collect();
        if let Some(result) = result {
            return Ok(result);
        }
    }
    Err(BaselineError::NotStrings(label.into()))
}

pub(super) fn count(raw: &Json, label: &str) -> Result<u64, BaselineError> {
    match raw {
        Json::Int(value) if *value >= 0 => {
            u64::try_from(*value).map_err(|_| BaselineError::IntegerRange(label.into()))
        }
        _ => Err(BaselineError::NotCount(label.into())),
    }
}
