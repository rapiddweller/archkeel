// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Copy only the import identities that an evaluated violation already cites.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_eval::{Outcome, Violation};

pub(crate) type Links = BTreeMap<String, BTreeSet<String>>;

pub(crate) fn add(links: &mut Links, outcome: &Outcome) {
    for violation in outcome.violations() {
        let imports = match violation {
            Violation::OutsideScope { cited, .. }
            | Violation::Undeclared { cited, .. }
            | Violation::Forbidden { cited, .. }
            | Violation::Peer { cited, .. }
            | Violation::Unrequired { cited, .. }
            | Violation::PrivateImport { cited, .. } => std::slice::from_ref(&cited.import),
            Violation::Cycle(cycle) => cycle.facts.as_slice(),
            Violation::Unassigned { .. }
            | Violation::NotAllowedChild { .. }
            | Violation::OuterLayer(_)
            | Violation::Construct(_) => &[],
        };
        for import in imports {
            links
                .entry(import.clone())
                .or_default()
                .insert(outcome.rule().to_owned());
        }
    }
}
