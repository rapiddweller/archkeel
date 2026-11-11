// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of the string comparisons (`_constructs`), apart from the plan and the stream of the
//! reply, so `records` does not hold what a construct record needs.

use archkeel_facts::data::ConstructData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::{
    ids::{EvidenceId, FactId},
    vocab::{Area, EvidenceClass},
    ConstructFact, Record,
};

use crate::cited::Cited;
use crate::collected::{sorted, Records};
use crate::kept::Pending;

/// The string comparison construct of `ForbiddenConstructKind`.
pub const STRING_LITERAL_COMPARE: &str = "string_literal_compare";

/// `_constructs`: one record for each written string comparison.
pub fn constructs(pending: &Pending, cited: &mut Cited, records: &mut Records) {
    let mut out = Vec::new();
    for (rel, kept) in &pending.kept {
        for (span, scope) in &kept.comparisons {
            let owner = match scope.as_deref().filter(|name| !name.is_empty()) {
                Some(name) => format!("{}.{name}", kept.module),
                None => kept.module.clone(),
            };
            let id = stable_id(
                "TSCONSTRUCT",
                &[
                    Part::Text(rel),
                    Part::Number(span.line),
                    Part::Number(span.column),
                    Part::Text(STRING_LITERAL_COMPARE),
                ],
            );
            let evidence = cited.cite(rel, span);
            let data = ConstructData {
                construct: STRING_LITERAL_COMPARE.to_owned(),
                form: None,
                handled: None,
                owner: owner.clone(),
            };
            out.push(Record {
                id: FactId::new(id),
                evidence_class: EvidenceClass::Fact,
                area: Area::Constructs,
                title: format!("{owner} compares a written string literal"),
                subjects: sorted(vec![owner]),
                evidence_ids: vec![EvidenceId::new(evidence)],
                fact_ids: Vec::new(),
                data: ConstructFact::StringLiteralCompare(data),
            });
        }
    }
    out.sort_by(|left, right| left.id.cmp(&right.id));
    records.constructs = out;
}
