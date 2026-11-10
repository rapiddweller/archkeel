// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reference record of a script write that no publication bounds
//! (`collect._script_runtime_effect`).

use archkeel_facts::identity::{stable_id, Part};
use archkeel_wire::reply::Record;
use serde_json::{json, Map};

use crate::cited::Cited;
use crate::script_records::Effect;

/// The record of one effect. Its `expression` is the excerpt that the evidence of the write has
/// when the record is made, as in Python.
pub fn effect_record(cited: &mut Cited, effect: &Effect) -> Record {
    let evidence = cited.cite(&effect.rel, &effect.span);
    let parts = [
        Part::Text(&effect.module),
        Part::Number(effect.span.line),
        Part::Number(effect.span.column),
    ];
    let id = stable_id("TS_RUNTIME_EFFECT", &parts);
    let mut data = Map::new();
    data.insert("source_module".to_owned(), json!(effect.module));
    data.insert("source_scope".to_owned(), json!(effect.module));
    data.insert("expression".to_owned(), json!(cited.excerpt(&evidence)));
    data.insert("status".to_owned(), json!("unresolved"));
    data.insert("targets".to_owned(), json!([]));
    data.insert("use".to_owned(), json!("value"));
    Record {
        id,
        evidence_class: "FACT",
        area: "source",
        kind: "script_namespace_effect",
        title: "Opaque script runtime effect".to_owned(),
        subjects: vec![effect.module.clone()],
        evidence_ids: vec![evidence],
        fact_ids: Vec::new(),
        data,
    }
}
