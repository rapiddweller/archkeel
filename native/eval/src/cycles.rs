// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `no_component_cycles` at component and at module level (slice S7, AD-384).
//!
//! Reference engine: `check/evaluation/rules.py` `_component_cycle_violations` and
//! `_module_cycle_violations` (AD-98). A component rule reports each component cycle that has a
//! member in its scope; a module rule reports each module cycle that has a member owned by a
//! component of its scope. The row cites each import between two members.

use std::collections::BTreeSet;

use archkeel_contract::{CycleLevel, NoComponentCycles};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_model::{Import, Level, Model};

use crate::violation::{Cyclic, Violation};

/// The violations of a `no_component_cycles` rule.
pub(crate) fn check(id: &str, rule: &NoComponentCycles, model: &Model) -> Vec<Violation> {
    let in_scope = |label: &str| {
        rule.components()
            .as_ref()
            .is_none_or(|labels| labels.iter().any(|l| l.as_text() == label))
    };
    let mut found: Vec<Violation> = match rule.level() {
        CycleLevel::Component => archkeel_model::cycles_of_components(model)
            .iter()
            .filter(|cycle| cycle.members().iter().any(|label| in_scope(label)))
            .map(|cycle| cyclic(id, cycle.members(), &cycle.imports(model), None))
            .collect(),
        CycleLevel::Module => {
            let scope: Vec<_> = model
                .contract()
                .components()
                .iter()
                .filter(|component| in_scope(component.label().as_text()))
                .collect();
            let imports = model.graph().imports();
            model
                .graph()
                .cycles()
                .iter()
                .filter(|cycle| cycle.level() == Level::Module)
                .filter(|cycle| {
                    rule.components().is_none()
                        || cycle
                            .members()
                            .iter()
                            .any(|member| scope.iter().any(|c| archkeel_model::claims(c, member)))
                })
                .map(|cycle| {
                    let members: BTreeSet<&str> =
                        cycle.members().iter().map(String::as_str).collect();
                    let closing: Vec<&Import> = imports
                        .iter()
                        .filter(|import| {
                            let ends = [import.source_module(), import.target_module()];
                            ends.iter().all(|end| members.contains(end)) && ends[0] != ends[1]
                        })
                        .collect();
                    let edges: BTreeSet<[String; 2]> = closing
                        .iter()
                        .map(|import| {
                            [import.source_module(), import.target_module()].map(str::to_owned)
                        })
                        .collect();
                    cyclic(
                        id,
                        cycle.members(),
                        &closing,
                        Some(edges.into_iter().collect()),
                    )
                })
                .collect()
        }
    };
    found.sort_by(|a, b| a.id().cmp(b.id()));
    found
}

/// One cycle violation: `stable_id("VIO", rule, *members)`, the cited imports and, for a module
/// cycle, its edges.
fn cyclic(
    rule: &str,
    members: &[String],
    imports: &[&Import],
    edges: Option<Vec<[String; 2]>>,
) -> Violation {
    let mut parts = vec![Part::Text(rule)];
    parts.extend(members.iter().map(|member| Part::Text(member)));
    let mut facts: Vec<String> = imports.iter().map(|i| i.id().to_owned()).collect();
    facts.sort();
    let mut evidence: Vec<String> = imports.iter().flat_map(|i| i.evidence().to_vec()).collect();
    evidence.sort();
    Violation::Cycle(Box::new(Cyclic {
        id: stable_id("VIO", &parts),
        rule: rule.to_owned(),
        members: members.to_vec(),
        facts,
        evidence,
        edges,
    }))
}
