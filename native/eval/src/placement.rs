// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Violations supported by proven class records; the scope proof holds back incomplete passes.

use archkeel_contract::SymbolPlacement;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::vocab::ClassKind;
use archkeel_model::{placement_violations, Model, Reason};

use crate::placement_row::PlacedClass;
use crate::violation::Violation;

pub(crate) fn check(
    id: &str,
    rule: &SymbolPlacement,
    model: &Model,
) -> Result<Vec<Violation>, Reason> {
    let mut found: Vec<_> = placement_violations(model, rule)?
        .into_iter()
        .map(|class| {
            Violation::SymbolPlacement(Box::new(PlacedClass {
                id: stable_id("VIO", &[Part::Text(id), Part::Text(&class.fact_id)]),
                rule: id.to_owned(),
                fact_id: class.fact_id,
                name: class.name,
                module: class.module,
                kind: ClassKind::as_str(class.kind).to_owned(),
                evidence: class.evidence,
            }))
        })
        .collect();
    found.sort_by(|a, b| Violation::id(a).cmp(Violation::id(b)));
    Ok(found)
}
