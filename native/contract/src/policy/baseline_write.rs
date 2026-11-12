// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Canonical Python baseline bytes. The checked types bound the output depth (AD-386).

use serde_json::{json, Map, Value};

use crate::model_declarations::BudgetName;
use crate::policy::baseline_value::{BaselineBudget, NameBudgetKind, ValidationBaseline};

/// Write schema 1.3.0 with `sort_keys=True`, `indent=2`, `ensure_ascii=False` and a line feed.
pub fn baseline_bytes(baseline: &ValidationBaseline) -> Vec<u8> {
    let mut budgets = Map::new();
    let mut keyed: std::collections::BTreeMap<&str, Map<String, Value>> =
        std::collections::BTreeMap::new();
    for budget in &baseline.budgets {
        match budget {
            BaselineBudget::Scalar { name, value } => {
                budgets.insert(scalar_key(*name).into(), json!(value));
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
    value.sort_all_objects();
    let mut out = String::new();
    crate::canonical::write(&mut out, &value, 0);
    out.push('\n');
    out.into_bytes()
}

fn scalar_key(name: BudgetName) -> &'static str {
    match name {
        BudgetName::CycleEdges => "cycle_edges",
        BudgetName::PrivateCrossings => "private_crossings",
        BudgetName::TypingPositions => "typing_positions",
        BudgetName::CallsUnresolved => "calls_unresolved",
        BudgetName::UntypedPrivateAccesses => "untyped_private_accesses",
        BudgetName::UnknownPositions => "unknown_positions",
    }
}

/// Hash canonical content, not the byte layout of the input file.
pub fn baseline_digest(baseline: &ValidationBaseline) -> String {
    crate::contract::digest_of(&baseline_bytes(baseline)).0
}
