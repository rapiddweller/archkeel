// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The UNKNOWN gap that a source collector writes: the one typed way to build it (AD-345).
//!
//! A statement collector (TypeScript, Rust) names a gap by its reason, the module it concerns and
//! the evidence that it cites. The id is the `stable_id` of the producer, so the same reason, the
//! same evidence and the same module give one record.

use crate::data::GapData;
use crate::identity::{stable_id, Part};
use crate::ids::{EvidenceId, FactId, ModuleName};
use crate::record::Record;
use crate::sections::GapFact;
use crate::vocab::{Area, EvidenceClass, ResolutionDimension};

impl GapData {
    /// The data of a gap with a reason and a module, and no other field.
    pub fn at(reason: &str, module: &str) -> Self {
        Self {
            code: None,
            reason: Some(reason.to_owned()),
            module: Some(ModuleName::new(module)),
            resolution_dimension: None,
            annotation: None,
            attribute: None,
            file: None,
            function: None,
            line: None,
            message: None,
            parameter: None,
            path: None,
            source_module: None,
            under_type_checking: None,
        }
    }
}

impl GapFact {
    /// A gap of the collection: a file, a scan root or a construct that the scan cannot read.
    pub fn collection(reason: &str, module: &str) -> Self {
        GapFact::CollectionGap(GapData::at(reason, module))
    }

    /// A gap of the resolution of imports: what the import leaves unknown is its target.
    pub fn resolution(reason: &str, module: &str) -> Self {
        let mut data = GapData::at(reason, module);
        data.resolution_dimension = Some(ResolutionDimension::Imports);
        GapFact::SourceResolutionGap(data)
    }
}

impl Record<GapFact> {
    /// The UNKNOWN record of a gap. An empty module is no subject, and no evidence is no id.
    pub fn unknown(
        id: FactId,
        reason: &str,
        evidence: Option<&str>,
        module: &str,
        gap: GapFact,
    ) -> Self {
        Self {
            id,
            evidence_class: EvidenceClass::Unknown,
            area: Area::Source,
            title: reason.to_owned(),
            subjects: Some(module)
                .filter(|m| !m.is_empty())
                .map(str::to_owned)
                .into_iter()
                .collect(),
            evidence_ids: evidence.map(EvidenceId::new).into_iter().collect(),
            fact_ids: Vec::new(),
            data: gap,
        }
    }

    /// The UNKNOWN record of a gap, with its id: the `stable_id` of the reason, the evidence and
    /// the module, so the same three give one record.
    pub fn unknown_gap(
        reason: &str,
        evidence: Option<&str>,
        module: &str,
        gap: GapFact,
    ) -> (String, Self) {
        let mut parts = vec![Part::Text(reason)];
        parts.extend(evidence.map(Part::Text));
        parts.push(Part::Text(module));
        let id = stable_id("UNKNOWN", &parts);
        let record = Self::unknown(FactId::new(id.clone()), reason, evidence, module, gap);
        (id, record)
    }
}

#[cfg(test)]
#[path = "gap_tests.rs"]
mod tests;
