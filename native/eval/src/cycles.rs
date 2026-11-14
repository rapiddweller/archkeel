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
use archkeel_model::{cycle_path, Import, Level, Link, Model};

use crate::violation::{CycleStep, Cyclic, Violation};

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
            .map(|cycle| {
                let path = steps(model, &cycle.links(model), true);
                cyclic(id, cycle.members(), &cycle.imports(model), None, path)
            })
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
                    let inside: Vec<(usize, &Import)> = imports
                        .iter()
                        .enumerate()
                        .filter(|(_, import)| {
                            let ends = [import.source_module(), import.target_module()];
                            ends.iter().all(|end| members.contains(end)) && ends[0] != ends[1]
                        })
                        .collect();
                    let closing: Vec<&Import> = inside.iter().map(|(_, import)| *import).collect();
                    let links: Vec<Link> = inside
                        .iter()
                        .map(|(index, import)| {
                            (
                                *index,
                                import.source_module().to_owned(),
                                import.target_module().to_owned(),
                            )
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
                        steps(model, &links, false),
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
    path: Vec<CycleStep>,
) -> Violation {
    let mut parts = vec![Part::Text(rule)];
    parts.extend(members.iter().map(|member| Part::Text(member)));
    let (facts, evidence) = cited(imports.iter().copied());
    Violation::Cycle(Box::new(Cyclic {
        id: stable_id("VIO", &parts),
        rule: rule.to_owned(),
        members: members.to_vec(),
        facts,
        evidence,
        edges,
        path,
    }))
}

/// The sorted ids of some imports and the sorted evidence of them, with each repeat.
fn cited<'a>(imports: impl Iterator<Item = &'a Import>) -> (Vec<String>, Vec<String>) {
    let (mut facts, mut evidence) = (Vec::new(), Vec::new());
    for import in imports {
        facts.push(import.id().to_owned());
        evidence.extend(import.evidence().iter().cloned());
    }
    facts.sort();
    evidence.sort();
    (facts, evidence)
}

/// The ordered path through a cycle, from the links between its members (AD-484). The model finds
/// the path; this function names the imports and the owners of each step. A component step names
/// the member by its label, so `by_label` reads the component id of the label.
fn steps(model: &Model, links: &[Link], by_label: bool) -> Vec<CycleStep> {
    let mut members: Vec<String> = links
        .iter()
        .flat_map(|(_, from, to)| [from.clone(), to.clone()])
        .collect();
    members.sort();
    members.dedup();
    let imports = model.graph().imports();
    let components = model.contract().components();
    let component_of = |name: &str| -> Option<String> {
        if by_label {
            return components
                .iter()
                .find(|component| component.label().as_text() == name)
                .map(|component| component.id().as_text().to_owned());
        }
        let mut owners = components
            .iter()
            .filter(|component| archkeel_model::claims(component, name));
        let first = owners.next()?;
        owners
            .next()
            .is_none()
            .then(|| first.id().as_text().to_owned())
    };
    cycle_path(&members, links)
        .into_iter()
        .map(|step| {
            let (facts, evidence) = cited(step.imports.iter().filter_map(|&i| imports.get(i)));
            CycleStep {
                from_component: component_of(&step.from),
                to_component: component_of(&step.to),
                from: step.from,
                to: step.to,
                imports: facts,
                evidence,
            }
        })
        .collect()
}
