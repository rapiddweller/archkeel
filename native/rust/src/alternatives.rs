// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `cfg` alternatives of one module: `#[cfg(a)] mod m;` and `#[cfg(not(a))] mod m;`.
//!
//! Rust refuses two modules of one name in one parent unless a `cfg` removes all but one of them.
//! So when every declaration of a name carries a `cfg`, the module is one of them, and the walk
//! reads all of them: an edge in any alternative is an edge of the crate. The `cfg` gives no gap
//! then, as it gives none for a feature that the manifest declares.

use crate::attrs::CFG_GATE_MODULE;
use crate::scan::{Child, Concern, Scan, Site};

/// Remove the gaps of the `cfg` on each declaration that has an alternative with a `cfg`.
pub fn release(scan: &mut Scan) {
    let released: Vec<&Site> = scan
        .children
        .iter()
        .filter(|child| {
            let same = |other: &&Child| other.name == child.name && other.inline == child.inline;
            let group: Vec<_> = scan.children.iter().filter(same).collect();
            group.len() > 1 && group.iter().all(|other| other.cfg_gate.is_some())
        })
        .filter_map(|child| child.cfg_gate.as_ref())
        .collect();
    let keep = |concern: &Concern| {
        !(concern.reason.starts_with(CFG_GATE_MODULE) && released.contains(&&concern.site))
    };
    let kept: Vec<Concern> = scan.concerns.iter().filter(|c| keep(c)).cloned().collect();
    scan.concerns = kept;
}

#[cfg(test)]
#[path = "alternatives_tests.rs"]
mod tests;
