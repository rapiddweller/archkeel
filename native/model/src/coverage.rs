// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the reply itself names as not seen (slices S1 and S2).
//!
//! This is the other side of the scope proof: not the proof that a run saw its whole scope (S4
//! makes `ScopeComplete`), but a fact that it did not. A fact of this kind can only turn a rule
//! into UNKNOWN, never into PASS, so it is safe before S4.
//!
//! Reference engine: `check/evaluation/evaluate.py` `coverage_payload` (status FAIL when `failures` or
//! `not paths`), `ir/coverage.py` `observation_complete`, and `check/pair_gaps.py`
//! `drop_allowed_pair_gaps`, which can drop a gap with a `source_module` and a different
//! `module` before the evaluation. Such a gap is not a certain fact here, so it is not counted.
//!
//! Slice S2 adds the unresolved imports that no collector gap names (`evaluate_source` appends an
//! `unknown_import_failure` for each). A gap that the contract can drop still names its site
//! here, so this count is never larger than the count of the reference engine.

use archkeel_facts::data::GapData;
use archkeel_facts::envelope::Coverage;
use archkeel_facts::sections::GapFact;

/// Why the reply proves that the scope of a run is not complete.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Incomplete {
    /// The collector selected no source file.
    NoSourceFiles,
    /// The collector reports gaps that no contract can drop (their number).
    CoverageGaps(usize),
    /// Imports that the collector cannot resolve and that no gap names (their number).
    UnknownImports(usize),
}

/// The incompleteness that the coverage of a reply proves, if any.
pub(crate) fn incomplete(coverage: &Coverage, unknown_imports: usize) -> Option<Incomplete> {
    if coverage.selected_files.is_empty() {
        return Some(Incomplete::NoSourceFiles);
    }
    let certain = coverage
        .gaps
        .iter()
        .filter(|gap| !droppable(data_of(&gap.data)))
        .count();
    if certain > 0 {
        return Some(Incomplete::CoverageGaps(certain));
    }
    (unknown_imports > 0).then_some(Incomplete::UnknownImports(unknown_imports))
}

/// True for a gap between two modules: the contract can allow it (`drop_allowed_pair_gaps`).
pub(crate) fn droppable(data: &GapData) -> bool {
    match (&data.source_module, &data.module) {
        (Some(source), Some(module)) => source != module,
        _ => false,
    }
}

pub(crate) fn data_of(gap: &GapFact) -> &GapData {
    match gap {
        GapFact::CollectionGap(data)
        | GapFact::SourceResolutionGap(data)
        | GapFact::DynamicImportLimit(data)
        | GapFact::PrivateAttributeAccessLimit(data)
        | GapFact::ExceptionGap { data, .. } => data,
    }
}
