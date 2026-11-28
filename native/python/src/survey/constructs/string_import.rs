// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The signal of a call that imports a module by a fixed string (AD-1440): the target and the line,
//! for a declaration. The owner is the module: the rule and the declaration name no function.

use std::collections::HashMap;

use archkeel_facts::data::SignalData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::sections::SignalFact;
use archkeel_facts::vocab::{Area, EvidenceClass, Signal};
use archkeel_facts::Record;
use ruff_text_size::TextRange;

use crate::module::{EvidenceMap, Module};

pub(super) fn signals(
    module: &Module,
    fixed: &HashMap<TextRange, String>,
    evidence: &mut EvidenceMap,
) -> Vec<Record<SignalFact>> {
    let mut sites: Vec<(&TextRange, &String)> = fixed.iter().collect();
    sites.sort_by_key(|(range, _)| range.start());
    sites
        .into_iter()
        .map(|(range, target)| {
            let node = Site(*range);
            let place = module.location(&node);
            let id = stable_id(
                "TYPE",
                &[
                    Part::Text(&module.rel),
                    Part::Number(place.line),
                    Part::Number(place.column),
                    Part::Text("string_import"),
                ],
            );
            let data = SignalData {
                annotation: None,
                expression: Some(target.clone()),
                line: Some(place.line),
                owner: module.name.clone(),
                positions: None,
                qualified_name: None,
                signal: Signal::StringImport,
                statement: None,
                tag: None,
            };
            Record {
                id: FactId::new(id),
                evidence_class: EvidenceClass::Fact,
                area: Area::TypeArchitecture,
                title: format!("{} uses string_import", module.name),
                subjects: vec![module.name.clone()],
                evidence_ids: vec![EvidenceId::new(module.evidence(evidence, &node))],
                fact_ids: Vec::new(),
                data: SignalFact::StringImport(data),
            }
        })
        .collect()
}

/// The range of a call, as a node for the location and the evidence.
struct Site(TextRange);

impl ruff_text_size::Ranged for Site {
    fn range(&self) -> TextRange {
        self.0
    }
}
