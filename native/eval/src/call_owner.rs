// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_contract::CallOwner;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_model::{call_owner_violations, Model, Reason};

use crate::call_owner_row::CallOwnerViolation;
use crate::violation::Violation;

pub(crate) fn check(id: &str, rule: &CallOwner, model: &Model) -> Result<Vec<Violation>, Reason> {
    let calls = call_owner_violations(model, rule)?;
    let mut violations = Vec::with_capacity(calls.len());
    for call in calls {
        let row = CallOwnerViolation {
            id: stable_id("VIO", &[Part::Text(id), Part::Text(call.fact_id)]),
            rule: id.to_owned(),
            fact_id: call.fact_id.to_owned(),
            source: call.source.to_owned(),
            target: call.target.to_owned(),
            evidence: call.evidence.to_vec(),
        };
        Vec::push(&mut violations, Violation::CallOwner(Box::new(row)));
    }
    violations.sort_by(|a, b| Violation::id(a).cmp(Violation::id(b)));
    Ok(violations)
}
