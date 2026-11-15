// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The coverage gaps of a reply as a reader needs them (AD-484): the id, the kind, the text and
//! the two modules of a pair gap. `whole` is the answer of the scope proof itself: the same
//! class as `coverage::incomplete` counts (`gap_effects::Class`), so a page never recomputes it.

use archkeel_facts::envelope::Coverage;

use crate::coverage::data_of;
use crate::gap_effects::Class;

/// One coverage gap of the reply.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CoverageGap {
    pub id: String,
    pub kind: String,
    pub title: String,
    /// The source module of a gap between two modules.
    pub source: Option<String>,
    /// The module of the gap.
    pub module: Option<String>,
    /// The gap leaves the whole scope unknown, so it holds each rule: no contract can drop it,
    /// and it states no effect (AD-564).
    pub whole: bool,
}

/// The coverage gaps of a reply, in the order of the reply.
pub(crate) fn coverage_gaps(coverage: &Coverage, classes: &[Class]) -> Vec<CoverageGap> {
    coverage
        .gaps
        .iter()
        .zip(classes)
        .map(|(gap, class)| {
            let data = data_of(&gap.data);
            CoverageGap {
                id: gap.id.as_str().to_owned(),
                kind: gap.kind().as_str().to_owned(),
                title: gap.title.clone(),
                source: data.source_module.as_ref().map(|m| m.as_str().to_owned()),
                module: data.module.as_ref().map(|m| m.as_str().to_owned()),
                whole: *class == Class::Whole,
            }
        })
        .collect()
}
