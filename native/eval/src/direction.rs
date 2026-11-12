// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The direction rule kinds (slice S5, AD-380): `forbidden_dependency`, `sibling_isolation`,
//! `complete_requires` and `layer_order`.
//!
//! The import matchers live in the model (`archkeel_model::forbidden`, `peers`, `crossings`), so
//! the violations here and the undecided positions of the scope proof read one judgement.
//!
//! Reference engine: `check/evaluation/rules.py:99` `_dependency_violations`, `:1387`
//! `_sibling_violations`, `:1877` `requires_violations` and `:2008` `_layer_order_violations`,
//! with `check/observation.py:612` `_layer_order_evidence` (the contract file that each
//! `layer_order` row cites).

use std::collections::{HashMap, HashSet};

use archkeel_contract::{CompleteRequires, ForbiddenDependency, LayerOrder, SiblingIsolation};
use archkeel_facts::identity::{stable_id, Part as IdPart};
use archkeel_model::{Input, Judged, Model, Part, Reason};

use crate::violation::{Layered, Violation};

/// The violations of a `forbidden_dependency` rule.
pub(crate) fn forbidden(id: &str, rule: &ForbiddenDependency, model: &Model) -> Vec<Violation> {
    sorted(
        archkeel_model::forbidden(model, rule)
            .into_iter()
            .filter(|(_, judged)| *judged == Judged::Fail)
            .map(|(import, _)| Violation::forbidden(id, import))
            .collect(),
    )
}

/// The violations of a `sibling_isolation` rule.
pub(crate) fn siblings(id: &str, rule: &SiblingIsolation, model: &Model) -> Vec<Violation> {
    sorted(
        archkeel_model::peers(model, rule)
            .into_iter()
            .map(|(import, source)| Violation::peer(id, source, import))
            .collect(),
    )
}

/// The violations of a `complete_requires` rule.
pub(crate) fn requires(id: &str, rule: &CompleteRequires, model: &Model) -> Vec<Violation> {
    sorted(
        archkeel_model::crossings(model, rule)
            .into_iter()
            .filter(|crossing| crossing.judged == Judged::Fail)
            .map(|crossing| {
                let labels = [crossing.source.label(), crossing.target.label()];
                Violation::unrequired(id, labels.map(|label| label.as_text()), crossing.import)
            })
            .collect(),
    )
}

/// The violations of a `layer_order` rule: each first `requires` entry of a selected source that
/// points to a component of an outer layer. A row cites the contract file; without its source the
/// reference engine drops the rows and gives UNKNOWN, so the rule has the named part.
pub(crate) fn layers(id: &str, rule: &LayerOrder, model: &Model) -> Result<Vec<Violation>, Reason> {
    let contract = model.contract();
    // `{layer: index}`: a repeated layer keeps its last index.
    let order: HashMap<&str, usize> = rule
        .layers()
        .iter()
        .enumerate()
        .map(|(index, layer)| (layer.as_str(), index))
        .collect();
    let by_label: HashMap<&str, &archkeel_contract::Component> = contract
        .components()
        .iter()
        .map(|component| (component.label().as_text(), component))
        .collect();
    // AD-385: the receipt and each row of an inside rule cite the inside contract file.
    if model.is_mount() {
        return Err(Part::MountedLayerOrder.into());
    }
    let receipt = stable_id("RULE-EVALUATION", &[IdPart::Text("root"), IdPart::Text(id)]);
    let mut found = Vec::new();
    for source in contract.components() {
        let selected = rule
            .components()
            .as_ref()
            .is_none_or(|labels| labels.contains(source.label()));
        let Some((source_layer, &inner)) = source
            .layer()
            .as_deref()
            .and_then(|layer| order.get(layer).map(|index| (layer, index)))
        else {
            continue;
        };
        if !selected {
            continue;
        }
        let mut seen: HashSet<&str> = HashSet::new();
        for entry in source.requires().iter().flatten() {
            let label = entry.component().as_text();
            if !seen.insert(label) {
                continue;
            }
            // The parser refuses a `requires` entry of an unknown label (`codec_contract.py:411`).
            let target = by_label
                .get(label)
                .ok_or(Reason::MissingInput(Input::Contract))?;
            let Some((target_layer, &outer)) = target
                .layer()
                .as_deref()
                .and_then(|layer| order.get(layer).map(|index| (layer, index)))
            else {
                continue;
            };
            if inner >= outer {
                continue;
            }
            let digest = contract.digest().as_text();
            let evidence = model.graph().settings().contract_evidence(digest);
            let evidence = evidence.ok_or(Reason::from(Part::ContractSource))?;
            let parts = [id, source.id().as_text(), target.id().as_text()].map(IdPart::Text);
            let mut provenance = source.provenance().clone();
            provenance.sort();
            found.push(Violation::OuterLayer(Box::new(Layered {
                id: stable_id("VIO-LAYER", &parts),
                rule: id.to_owned(),
                receipt: receipt.clone(),
                evidence: evidence.to_owned(),
                provenance,
                source_component: source.label().as_text().to_owned(),
                target_component: label.to_owned(),
                source_layer: source_layer.to_owned(),
                target_layer: target_layer.to_owned(),
                rationale: entry.rationale().clone(),
            })));
        }
    }
    Ok(sorted(found))
}

fn sorted(mut violations: Vec<Violation>) -> Vec<Violation> {
    violations.sort_by(|a, b| a.id().cmp(b.id()));
    violations
}
