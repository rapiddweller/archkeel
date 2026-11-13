// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reference record of a script write that no publication bounds
//! (`collect._script_runtime_effect`).

use archkeel_facts::data::ReferenceData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName};
use archkeel_facts::vocab::{Area, EvidenceClass, Status, Use};
use archkeel_facts::{Record, ReferenceFact};

use crate::cited::Cited;
use crate::script_records::Effect;

/// The record of one effect. Its `expression` is the excerpt that the evidence of the write has
/// when the record is made, as in Python.
pub(crate) fn effect_record(cited: &mut Cited, effect: &Effect) -> Record<ReferenceFact> {
    let evidence = cited.cite(&effect.rel, &effect.span);
    let parts = [
        Part::Text(&effect.module),
        Part::Number(effect.span.line),
        Part::Number(effect.span.column),
    ];
    let id = stable_id("TS_RUNTIME_EFFECT", &parts);
    let mut data = ReferenceData::new(
        cited.excerpt(&evidence),
        (ModuleName::new(&effect.module), effect.module.clone()),
        (Status::Unresolved, Use::Value),
        Vec::new(),
    );
    data.candidate_count = None;
    data.candidates_truncated = None;
    Record {
        id: FactId::new(id),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: "Opaque script runtime effect".to_owned(),
        subjects: vec![effect.module.clone()],
        evidence_ids: vec![EvidenceId::new(evidence)],
        fact_ids: Vec::new(),
        data: ReferenceFact::ScriptNamespaceEffect(data),
    }
}
