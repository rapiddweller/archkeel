// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Copy only the import identities that an evaluated violation already cites.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_eval::{CycleStep, Outcome, Violation};

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
            Violation::Publication(found) => std::slice::from_ref(&found.cited.import),
            Violation::Cycle(cycle) => cycle.facts.as_slice(),
            Violation::Unassigned { .. }
            | Violation::NotAllowedChild { .. }
            | Violation::OuterLayer(_)
            | Violation::Construct(_)
            | Violation::BoundaryType(_)
            | Violation::ProtocolDeclaration(_)
            | Violation::CallOwner { .. }
            | Violation::ForbiddenArgument { .. }
            | Violation::UnusedPublic(_)
            | Violation::SymbolPlacement(_) => &[],
        };
        let hops: &[CycleStep] = match violation {
            Violation::Forbidden { chain, .. } => chain,
            _ => &[],
        };
        let rule = outcome.rule();
        for import in imports {
            link(links, import, rule);
        }
        for step in hops {
            for import in &step.imports {
                link(links, import, rule);
            }
        }
    }
}

fn link(links: &mut Links, import: &str, rule: &str) {
    links
        .entry(import.to_owned())
        .or_default()
        .insert(rule.to_owned());
}
