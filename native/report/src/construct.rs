// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The original evidence and text of forbidden-construct rows (AD-408).

use archkeel_eval::ConstructViolation;
use serde_json::{json, Value};

/// The canonical decoded row of a forbidden construct. It carries no verdict or PASS claim.
pub fn construct_row(row: &ConstructViolation) -> Value {
    let (title, data) = match &row.selector {
        Some(selector) => {
            let role = serde_json::to_value(selector.role()).unwrap_or(Value::Null);
            let role_text = role.as_str().unwrap_or_default();
            let member = selector
                .member()
                .as_deref()
                .unwrap_or(selector.receiver().as_text());
            (
                format!("{} uses selected {role_text} on {member}", row.owner),
                json!({"source": row.source, "selector_role": role, "receiver": selector.receiver().as_text(),
                "member": selector.member(), "literal": selector.literal()}),
            )
        }
        None => (
            format!("{} uses forbidden {}", row.owner, row.construct),
            json!({"source": row.source, "construct": row.construct}),
        ),
    };
    json!({"id": row.id, "evidence_class": "VIOLATION", "area": "type_architecture",
        "kind": "forbidden_construct", "title": title, "subjects": [row.owner],
        "evidence_ids": row.evidence, "rule_ids": [row.rule], "fact_ids": row.facts,
        "provenance": row.provenance, "data": data})
}
