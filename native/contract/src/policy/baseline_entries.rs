// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Validation of baseline entries and measurement budgets (AD-386).

use crate::json::{field, has, keys, Json};
use crate::model_declarations::BudgetName;
use crate::policy::amendment::blank;
use crate::policy::baseline_value::{
    count, exact, object, required, strings, BaselineBudget, BaselineError, BaselineFingerprint,
    BaselineRole, BaselineViolation, NameBudgetKind,
};

pub(super) fn violation(
    raw: &Json,
    label: &str,
    with_roles: bool,
) -> Result<BaselineViolation, BaselineError> {
    let value = object(raw, label)?;
    let mut fields = vec!["rules", "subjects", "count"];
    if with_roles && has(value, "roles") {
        fields.push("roles");
    }
    exact(value, &fields, label)?;
    let count_label = format!("{label}.count");
    let occurrences = count(required(value, "count"), &count_label)?;
    if occurrences == 0 {
        return Err(BaselineError::ZeroCount(count_label));
    }
    let roles = match field(value, "roles") {
        Some(raw) => roles(raw, &format!("{label}.roles"))?,
        None => Vec::new(),
    };
    let mut rules = strings(required(value, "rules"), &format!("{label}.rules"))?;
    let mut subjects = strings(required(value, "subjects"), &format!("{label}.subjects"))?;
    rules.sort();
    subjects.sort();
    Ok(BaselineViolation {
        fingerprint: BaselineFingerprint { rules, subjects },
        count: occurrences,
        roles,
    })
}

fn text(raw: &Json, label: &str) -> Result<String, BaselineError> {
    match raw {
        Json::Text(value) => Ok(value.clone()),
        _ => Err(BaselineError::NotString(label.into())),
    }
}

fn roles(raw: &Json, label: &str) -> Result<Vec<BaselineRole>, BaselineError> {
    let Json::Array(values) = raw else {
        return Err(BaselineError::NotArray(label.into()));
    };
    let mut parsed = Vec::new();
    for (index, raw) in values.iter().enumerate() {
        let role_label = format!("{label}[{index}]");
        let value = object(raw, &role_label)?;
        exact(value, &["source", "target"], &role_label)?;
        parsed.push(BaselineRole {
            source: text(required(value, "source"), &format!("{role_label}.source"))?,
            target: text(required(value, "target"), &format!("{role_label}.target"))?,
        });
    }
    parsed.sort_by(|a, b| (&a.source, &a.target).cmp(&(&b.source, &b.target)));
    if parsed.windows(2).any(|pair| pair.first() == pair.get(1)) {
        return Err(BaselineError::RepeatedRole(label.into()));
    }
    Ok(parsed)
}

pub(super) fn budgets(raw: &Json, with_names: bool) -> Result<Vec<BaselineBudget>, BaselineError> {
    let value = object(raw, "baseline.budgets")?;
    let mut names: Vec<&str> = keys(value).collect();
    names.sort_unstable();
    let mut budgets = Vec::new();
    for name in names {
        let label = format!("baseline.budgets.{name}");
        let raw = required(value, name);
        match (with_names, name) {
            (true, "facade_names") => {
                budgets.extend(name_budgets(NameBudgetKind::FacadeNames, raw, &label)?)
            }
            (true, "coupling_names") => {
                budgets.extend(name_budgets(NameBudgetKind::CouplingNames, raw, &label)?)
            }
            _ => {
                let name = scalar_name(name)
                    .ok_or_else(|| BaselineError::UnsupportedBudget(label.clone()))?;
                budgets.push(BaselineBudget::Scalar {
                    name,
                    value: count(raw, &label)?,
                });
            }
        }
    }
    Ok(budgets)
}

fn scalar_name(name: &str) -> Option<BudgetName> {
    match name {
        "cycle_edges" => Some(BudgetName::CycleEdges),
        "private_crossings" => Some(BudgetName::PrivateCrossings),
        "typing_positions" => Some(BudgetName::TypingPositions),
        "calls_unresolved" => Some(BudgetName::CallsUnresolved),
        "untyped_private_accesses" => Some(BudgetName::UntypedPrivateAccesses),
        "unknown_positions" => Some(BudgetName::UnknownPositions),
        _ => None,
    }
}

fn name_budgets(
    kind: NameBudgetKind,
    raw: &Json,
    label: &str,
) -> Result<Vec<BaselineBudget>, BaselineError> {
    let value = object(raw, label)?;
    let mut keys: Vec<&str> = keys(value).collect();
    keys.sort_unstable();
    let mut budgets = Vec::new();
    for key in keys {
        let names_label = format!("{label}.{key}");
        let names = strings(required(value, key), &names_label)?;
        if names.windows(2).any(|pair| pair.first() >= pair.get(1)) {
            return Err(BaselineError::UnsortedNames(names_label));
        }
        if blank(key) {
            return Err(BaselineError::Empty(label.into()));
        }
        budgets.push(BaselineBudget::Names {
            kind,
            key: key.into(),
            names,
        });
    }
    Ok(budgets)
}
