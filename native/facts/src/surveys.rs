// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A check that each import survey shares (the Python survey, AD-450; the Dart survey, AD-468).
//! The collectors run it in their own check (AD-688); the store does not, because a reply of
//! another collector may name an unknown that is not a coverage gap.

use crate::envelope::Facts;
use crate::Section;

/// The coverage gaps are the records of the `unknowns` section, each once: a gap that only one
/// of them names is a partial claim.
pub fn gaps_are_unknowns(facts: &Facts) -> Result<(), String> {
    let mut unknowns: Vec<&str> = facts
        .sections
        .iter()
        .filter_map(|section| match section {
            Section::Unknowns(records) => Some(records),
            _ => None,
        })
        .flatten()
        .map(|record| record.id.as_str())
        .collect();
    let mut gaps: Vec<&str> = facts
        .coverage
        .gaps
        .iter()
        .map(|gap| gap.id.as_str())
        .collect();
    unknowns.sort_unstable();
    gaps.sort_unstable();
    if unknowns == gaps {
        Ok(())
    } else {
        Err("the coverage gaps must be the unknowns of the survey".to_owned())
    }
}
