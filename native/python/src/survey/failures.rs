// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The UNKNOWN records of a file that the survey does not read as a module.
//!
//! A failure is the record of `source.parse_sources`, a shadowed module is `_shadowed_gap`
//! (#797), and a file that the native collector does not see (`Unseen`) is a collection gap that
//! names it, so that nothing unseen is silent (AD-367 points 4 and 6).

use archkeel_facts::data::GapData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, EvidenceClass, ExceptionName};
use archkeel_facts::{GapFact, Record};

use crate::names::Shadowed;
use crate::parse::ParseFailure as Failure;

/// `GapTitle.FILE_FAILURE`.
const FILE_FAILURE: &str = " could not be analyzed";

/// The message of `OSError.strerror` for a file that does not exist.
pub(super) const NOT_FOUND: &str = "No such file or directory";

/// A gap record with the sorted subjects and evidence ids of `classified`.
pub(super) fn record(
    (id, area, title): (String, Area, String),
    subjects: Vec<String>,
    evidence_ids: Vec<EvidenceId>,
    fact_ids: Vec<FactId>,
    data: GapFact,
) -> Record<GapFact> {
    let mut subjects: Vec<String> = subjects.into_iter().filter(|s| !s.is_empty()).collect();
    subjects.sort();
    let mut evidence_ids = evidence_ids;
    evidence_ids.sort_by(|a, b| a.as_str().cmp(b.as_str()));
    Record {
        id: FactId::new(id),
        evidence_class: EvidenceClass::Unknown,
        area,
        title,
        subjects,
        evidence_ids,
        fact_ids,
        data,
    }
}

/// The data of a file problem: the file, the line and the message.
fn file_data(rel: &str, line: i64, message: &str) -> GapData {
    GapData {
        reason: None,
        module: None,
        file: Some(rel.to_owned()),
        line: Some(line),
        message: Some(message.to_owned()),
        ..GapData::at("", "")
    }
}

/// The failure record of a file that does not read, decode, parse or have a module name.
pub(super) fn failure(rel: &str, failure: &Failure) -> Record<GapFact> {
    let line = i64::try_from(failure.line).unwrap_or(i64::MAX);
    let name = failure.exception.as_str();
    let parts = [
        Part::Text(rel),
        Part::Number(line),
        Part::Text(name),
        Part::Text(&failure.message),
    ];
    let data = GapFact::ExceptionGap {
        exception: failure.exception,
        data: file_data(rel, line, &failure.message),
    };
    let head = (
        stable_id("COVERAGE", &parts),
        Area::AnalysisCoverage,
        format!("{rel}:{line}{FILE_FAILURE}"),
    );
    record(head, vec![rel.to_owned()], Vec::new(), Vec::new(), data)
}

/// The failure of a file before its parse, on line 1 (`OSError`, decode, module name).
pub(super) fn early(exception: ExceptionName, message: &str) -> Failure {
    Failure {
        exception,
        line: 1,
        message: message.to_owned(),
    }
}

/// `_shadowed_gap`: a module that a package of the same name shadows (#797). The name
/// `ShadowedModule` exists in protocol 10.0.0 only (AD-367 point 9).
pub(super) fn shadowed(item: &Shadowed) -> Record<GapFact> {
    let data = GapFact::ExceptionGap {
        exception: ExceptionName::ShadowedModule,
        data: file_data(&item.file, 1, &item.message()),
    };
    let head = (item.id(), Area::AnalysisCoverage, item.title());
    record(head, vec![item.file.clone()], Vec::new(), Vec::new(), data)
}

/// The collection gap of a file that the native collector does not see: its reason names it.
pub(super) fn unseen(rel: &str, reason: &str) -> Record<GapFact> {
    file_gap(rel, reason, format!("{rel}:1{FILE_FAILURE}"))
}

/// The collection gap of one file with its title.
pub(super) fn file_gap(rel: &str, reason: &str, title: String) -> Record<GapFact> {
    let mut data = GapData::at(reason, "");
    data.module = None;
    data.file = Some(rel.to_owned());
    let parts = [
        Part::Text(rel),
        Part::Text("collection_gap"),
        Part::Text(reason),
    ];
    let head = (stable_id("COVERAGE", &parts), Area::AnalysisCoverage, title);
    record(
        head,
        vec![rel.to_owned()],
        Vec::new(),
        Vec::new(),
        GapFact::CollectionGap(data),
    )
}

#[cfg(test)]
#[path = "failures_tests.rs"]
mod tests;
