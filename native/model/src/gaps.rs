// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The coverage gaps of a reply as a reader needs them (AD-484): the id, the kind, the text and
//! the two modules of a pair gap. `holds_run` is the answer of the scope proof itself: the
//! same filter as `coverage::incomplete`, so a page never recomputes it.

use archkeel_facts::envelope::Coverage;

use crate::coverage::{data_of, droppable};

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
    /// The gap makes the scope of the run incomplete: no contract can drop it.
    pub holds_run: bool,
}

/// The coverage gaps of a reply, in the order of the reply.
pub(crate) fn coverage_gaps(coverage: &Coverage) -> Vec<CoverageGap> {
    coverage
        .gaps
        .iter()
        .map(|gap| {
            let data = data_of(&gap.data);
            CoverageGap {
                id: gap.id.as_str().to_owned(),
                kind: gap.kind().as_str().to_owned(),
                title: gap.title.clone(),
                source: data.source_module.as_ref().map(|m| m.as_str().to_owned()),
                module: data.module.as_ref().map(|m| m.as_str().to_owned()),
                holds_run: !droppable(data),
            }
        })
        .collect()
}
