// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Canonical Python baseline bytes. The checked types bound the output depth (AD-386).

use serde_json::{json, Map, Value};

use crate::model_declarations::BudgetName;
use crate::policy::baseline_value::{
    AcceptedUnknown, BaselineBudget, NameBudgetKind, ValidationBaseline,
};

/// Write schema 1.3.0, or 1.4.0 (1.5.0 when it names every cause) when the baseline has an `unknowns` list, with `sort_keys=True`, `indent=2`, `ensure_ascii=False` and a line feed.
pub fn baseline_bytes(baseline: &ValidationBaseline) -> Vec<u8> {
    let mut budgets = Map::new();
    let mut keyed: std::collections::BTreeMap<&str, Map<String, Value>> =
        std::collections::BTreeMap::new();
    for budget in &baseline.budgets {
        match budget {
            BaselineBudget::Scalar { name, value } => {
                budgets.insert(budget_word(*name).into(), json!(value));
            }
            BaselineBudget::Names { kind, key, names } => {
                let name = match kind {
                    NameBudgetKind::FacadeNames => "facade_names",
                    NameBudgetKind::CouplingNames => "coupling_names",
                };
                keyed
                    .entry(name)
                    .or_default()
                    .insert(key.clone(), json!(names));
            }
        }
    }
    for (name, values) in keyed {
        budgets.insert(name.into(), Value::Object(values));
    }
    let violations: Vec<Value> = baseline
        .violations
        .iter()
        .map(|item| {
            let mut value = json!({
                "rules": item.fingerprint.rules,
                "subjects": item.fingerprint.subjects,
                "count": item.count,
            });
            if !item.roles.is_empty() {
                value["roles"] = json!(item.roles);
            }
            value
        })
        .collect();
    let mut value =
        json!({ "schema_version": "1.3.0", "violations": violations, "budgets": budgets });
    if let Some(unknowns) = &baseline.unknowns {
        value["schema_version"] = json!(if baseline.all_causes {
            "1.5.0"
        } else {
            "1.4.0"
        });
        value["unknowns"] = Value::Array(unknowns.iter().map(unknown).collect());
    }
    value.sort_all_objects();
    let mut out = String::new();
    crate::canonical::write(&mut out, &value, 0);
    out.push('\n');
    out.into_bytes()
}

/// One entry: `count` only above 1, so one entry has one form (AD-546).
fn unknown(item: &AcceptedUnknown) -> Value {
    let mut value = json!({
        "kind": item.kind,
        "subject": item.subject,
        "reason": item.reason,
    });
    if item.count > 1 {
        value["count"] = json!(item.count);
    }
    value
}

/// The word of a scalar budget in the file (AD-546: the core names a budget with it).
pub fn budget_word(name: BudgetName) -> &'static str {
    match name {
        BudgetName::CycleEdges => "cycle_edges",
        BudgetName::PrivateCrossings => "private_crossings",
        BudgetName::TypingPositions => "typing_positions",
        BudgetName::CallsUnresolved => "calls_unresolved",
        BudgetName::UntypedPrivateAccesses => "untyped_private_accesses",
        BudgetName::UnknownPositions => "unknown_positions",
    }
}
