// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rules that a dropped pair gap can change (AD-418).
//!
//! The drop rule (`pair_gaps.rs`, `check/pair_gaps.py`) drops a gap `a -> b` only when both ends
//! have one owner, the owners are one component or `a`'s owner requires `b`'s owner with an entry
//! without `through`, no rule names an end by its selector text, and the edge closes no cycle of
//! an active cycle level. The reference engine then forgets the gap. The core does not: the drop
//! rule reads selector texts, not the sides of a rule (review B1 of #1084), so a whole-component
//! side can still read the edge. A dropped gap holds each rule whose reading it can change, by
//! the readings of AD-384 point 5, with two kinds whose reading the drop rule itself proves:
//!
//! - `no_component_cycles`: the drop rule keeps each gap whose target reaches its source in the
//!   graph of the known imports plus every pair gap, at module level when the contract has a
//!   module cycle rule and at component level when it has another one. The cycle rows read the
//!   same imports (`cycles.rs`, `component_cycles.rs`). An edge whose target cannot reach its
//!   source makes no cycle and joins no two members of one cycle, so no cycle and no cited import
//!   changes. One component adds no component edge (`component_cycles.rs` skips a pair with one
//!   owner).
//! - `complete_requires`: a dropped edge lies in one component, which `crossings` skips, or
//!   follows a `requires` entry without `through`, which `assessment` judges PASS. So it adds no
//!   FAIL and no undecided position, and the receipt reads no edge.
//!
//! Both proofs need both ends to be modules of the reply: an end that the scan did not see can
//! have imports that no reach saw, so such a gap holds every rule, as a kept one does.
//!
//! Every other kind reads as for a kept gap: a dropped gap holds a `forbidden_dependency` rule
//! when its ends lie on the sides, which the drop rule does not check.

use archkeel_contract::Rule;

use crate::pair_gaps::{PairGap, Reads};

/// True when the dropped gap can change what the rule reads. A free function, not a method:
/// the collector cannot place a method of an `impl` block of another file (AD-357).
pub(crate) fn holds(gap: &PairGap, rule: &Rule, reading: &Reads<'_>) -> bool {
    match rule {
        // An end that the scan did not see can have edges that no reach saw.
        Rule::NoComponentCycles(_) | Rule::CompleteRequires(_) => !gap.observed,
        _ => gap.holds(reading),
    }
}

#[cfg(test)]
#[path = "dropped_gaps_tests.rs"]
mod tests;
