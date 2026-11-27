// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Typed baseline content and field validation (AD-386).

use std::fmt;

use crate::json::{field, keys, Json, Object};
use crate::model_declarations::BudgetName;

/// Refuse larger input before the JSON reader allocates a tree.
pub const MAX_BASELINE_BYTES: usize = 16 * 1024 * 1024;

record!(
    pub(crate),
    /// Sorted rule ids and subjects. Repeated members remain part of the identity.
    BaselineFingerprint {
        /// The rule ids.
        rules: Vec<String>,
        /// The sorted subjects of the rules.
        subjects: Vec<String>,
    }
);

record!(
    pub(crate),
    /// Direction evidence, separate from the fingerprint.
    BaselineRole {
        /// The selector of the modules that the rule judges.
        source: String,
        /// The target side of the direction evidence.
        target: String,
    }
);

record!(
    pub(crate),
    /// One checked debt entry. Only the codec can make one.
    BaselineViolation {
        /// The rules and subjects that identify the entry.
        fingerprint: BaselineFingerprint,
        /// How many violations the baseline accepts.
        count: u64,
        /// The direction evidence of the entry.
        roles: Vec<BaselineRole>,
    }
);

closed_enum!(
    /// The kind of names that a keyed budget lists.
    NameBudgetKind {
        /// The names of a facade.
        FacadeNames,
        /// The names that one component imports from another.
        CouplingNames,
    }
);

/// A scalar or keyed budget. A keyed value is the length of its names, never another count.
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
pub enum BaselineBudget {
    /// A budget that is one count.
    Scalar {
        /// The name of the budget.
        name: BudgetName,
        /// The count that the baseline accepts.
        value: u64,
    },
    /// A budget that is a list of names.
    Names {
        /// The kind of the names.
        kind: NameBudgetKind,
        /// The key of the budget, such as a facade or a component.
        key: String,
        /// The names that the baseline accepts, sorted.
        names: Vec<String>,
    },
}

record!(
    pub(crate),
    /// One accepted UNKNOWN (schema 1.4.0, AD-546): what it is, not where it is. There is no line,
    /// evidence id or digest. The count is how many equal entries the run has; 1 is not written.
    AcceptedUnknown {
        /// The kind of the value.
        kind: String,
        /// The subject that the item is about.
        subject: String,
        /// Why it holds or fails.
        reason: String,
        /// How many violations the baseline accepts.
        count: u64,
    }
);

impl AcceptedUnknown {
    /// An entry with at least one occurrence.
    pub fn new(
        kind: String,
        subject: String,
        reason: String,
        count: u64,
    ) -> Result<AcceptedUnknown, BaselineError> {
        if count == 0 {
            return Err(BaselineError::ZeroCount("accepted unknown".into()));
        }
        Ok(AcceptedUnknown {
            kind,
            subject,
            reason,
            count,
        })
    }

    /// The order and identity of an entry: kind, subject, reason.
    pub fn identity(&self) -> (&str, &str, &str) {
        (&self.kind, &self.subject, &self.reason)
    }
}

record!(
    pub(crate),
    /// Checked baseline content, sorted as Python sorts it. No rule or staleness check occurs.
    /// `unknowns` is `None` for schema 1.0.0 to 1.3.0: such a file accepts no UNKNOWN (AD-546).
    ValidationBaseline {
        /// The checked debt entries.
        violations: Vec<BaselineViolation>,
        /// The checked budgets.
        budgets: Vec<BaselineBudget>,
        /// The checked accepted UNKNOWN entries.
        unknowns: Option<Vec<AcceptedUnknown>>,
        /// True for schema 1.5.0: the entries name every cause of an UNKNOWN rule. A file of schema 1.4.0
        /// names the first cause only, so the compare leaves the other causes of a rule out (AD-1290).
        all_causes: bool,
    }
);

impl BaselineViolation {
    /// A violation entry of a run. The lists are sorted as the reader sorts them.
    pub fn new(
        mut rules: Vec<String>,
        mut subjects: Vec<String>,
        count: u64,
        mut roles: Vec<BaselineRole>,
    ) -> BaselineViolation {
        rules.sort();
        subjects.sort();
        roles.sort_by(|a, b| (&a.source, &a.target).cmp(&(&b.source, &b.target)));
        roles.dedup();
        BaselineViolation {
            fingerprint: BaselineFingerprint { rules, subjects },
            count,
            roles,
        }
    }
}

impl BaselineRole {
    /// The direction of one violation.
    pub fn new(source: String, target: String) -> BaselineRole {
        BaselineRole { source, target }
    }
}

impl ValidationBaseline {
    /// The baseline that a run writes: schema 1.5.0 with its accepted UNKNOWN entries. The
    /// entries are sorted by (kind, subject, reason) and by fingerprint, so one run gives one byte
    /// string (AD-546).
    pub fn of_run(
        mut violations: Vec<BaselineViolation>,
        budgets: Vec<BaselineBudget>,
        mut unknowns: Vec<AcceptedUnknown>,
    ) -> ValidationBaseline {
        violations.sort_by(|a, b| {
            (&a.fingerprint.rules, &a.fingerprint.subjects)
                .cmp(&(&b.fingerprint.rules, &b.fingerprint.subjects))
        });
        unknowns.sort_by(|a, b| a.identity().cmp(&b.identity()));
        ValidationBaseline {
            violations,
            budgets,
            unknowns: Some(unknowns),
            all_causes: true,
        }
    }
}

/// A baseline validation failure. Labels are paths into the input, not unchecked field maps.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BaselineError {
    /// The text is not JSON.
    Json(String),
    /// An object repeats a key.
    DuplicateKey(String),
    /// The text is larger than the limit.
    TooLarge,
    /// An integer is outside the range that the baseline accepts.
    IntegerRange(String),
    /// The value at the path must be an object.
    NotObject(String),
    /// The schema version is not supported.
    UnsupportedSchema(String),
    /// The keys of the object differ from the keys that the schema fixes.
    FieldsMismatch(String),
    /// The value at the path must be an array.
    NotArray(String),
    /// The value at the path must be a string.
    NotString(String),
    /// The value at the path must be an array of strings.
    NotStrings(String),
    /// The value at the path must be a count.
    NotCount(String),
    /// The count at the path is zero.
    ZeroCount(String),
    /// The list at the path is empty.
    Empty(String),
    /// A role appears twice.
    RepeatedRole(String),
    /// Two entries have the same fingerprint.
    RepeatedFingerprint {
        /// The index of the second entry.
        index: usize,
        /// The index of the first entry.
        first: usize,
        /// The repeated name.
        name: String,
    },
    /// The budget is not one that the baseline supports.
    UnsupportedBudget(String),
    /// The names at the path are not in sorted order.
    UnsortedNames(String),
    /// An accepted UNKNOWN that repeats an earlier entry, or does not follow it in order.
    UnorderedUnknown {
        /// The index of the entry.
        index: usize,
        /// True when the entry repeats an earlier one, false when it is out of order.
        repeated: bool,
        /// The name of the entry.
        name: String,
    },
}

impl fmt::Display for BaselineError {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(text) | Self::DuplicateKey(text) => out.write_str(text),
            Self::TooLarge => write!(out, "baseline exceeds the {MAX_BASELINE_BYTES}-byte limit"),
            Self::IntegerRange(label) => write!(out, "{label} exceeds the unsigned 64-bit integer range"),
            Self::NotObject(label) => write!(out, "{label} must be an object"),
            Self::UnsupportedSchema(value) => write!(out, "baseline schema {value} cannot be read as 1.0.0, 1.1.0, 1.2.0, 1.3.0, 1.4.0, 1.5.0"),
            Self::UnorderedUnknown { index, repeated: true, name } => write!(out, "baseline.unknowns[{index}] repeats an earlier entry, {name}; give it one count instead"),
            Self::UnorderedUnknown { index, repeated: false, name } => write!(out, "baseline.unknowns[{index}], {name}, is not sorted by kind, subject and reason"),
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
