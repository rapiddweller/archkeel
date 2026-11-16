// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declared structure of the contract tree as display rows (AD-594): each `requires` entry
//! with the number of observed imports that use it, and the layers of each `layer_order` rule.
//! It makes no decision: the rules decide, and these rows only show what the contract states.

use std::collections::BTreeMap;

use archkeel_contract::{head_of, Rule};
use archkeel_model::ModelTree;
use schemars::JsonSchema;
use serde::Serialize;

/// What a `requires` entry states besides its two components.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct Declared {
    pub(crate) rationale: String,
    pub(crate) through: Vec<String>,
}

/// One `requires` entry: the two components by id, and the observed imports that use it.
#[derive(Debug, PartialEq, Eq, Serialize, JsonSchema)]
pub(crate) struct Require {
    pub(crate) source: String,
    pub(crate) target: String,
    /// Zero says that no observed import uses the permission.
    pub(crate) imports: usize,
    /// Why the contract allows the pair.
    pub(crate) rationale: String,
    /// The selectors that an import of the pair must pass through; empty when the entry names none.
    pub(crate) through: Vec<String>,
}

/// The layers of one `layer_order` rule, from the inner layer to the outer layer.
#[derive(Serialize, JsonSchema)]
pub(crate) struct LayerOrder {
    rule: String,
    layers: Vec<String>,
}

/// Each declared pair of the tree, by component id, with its rationale and its ports. A label is
/// local to its contract.
pub(crate) fn pairs(models: &ModelTree) -> BTreeMap<(String, String), Declared> {
    let mut pairs = BTreeMap::new();
    for model in models.models() {
        for (_, component) in model.components().iter() {
            let targets = component.requires().iter().flatten().filter_map(|entry| {
                let id = model.component(entry.component().as_text())?;
                Some((model.components().get(id)?, entry))
            });
            pairs.extend(targets.map(|(target, entry)| {
                let declared = Declared {
                    rationale: entry.rationale().clone(),
                    through: entry
                        .through()
                        .iter()
                        .map(|s| s.as_text().to_owned())
                        .collect(),
                };
                let key = (
                    component.id().as_text().to_owned(),
                    target.id().as_text().to_owned(),
                );
                (key, declared)
            }));
        }
    }
    pairs
}

/// The rows of the declared pairs. An import between two components counts for each pair of
/// their ancestors too: a `requires` entry of a component with an inside contract covers the
/// imports of its sub-components.
pub(crate) fn requires<'a>(
    pairs: BTreeMap<(String, String), Declared>,
    parents: &BTreeMap<&'a str, &'a str>,
    observed: impl Iterator<Item = (&'a str, &'a str, usize)>,
) -> Vec<Require> {
    let chain = |start: &'a str| std::iter::successors(Some(start), |id| parents.get(id).copied());
    let mut sums: BTreeMap<(&str, &str), usize> = BTreeMap::new();
    for (source, target, count) in observed {
        for from in chain(source) {
            for to in chain(target).filter(|to| *to != from) {
                *sums.entry((from, to)).or_default() += count;
            }
        }
    }
    pairs
        .into_iter()
        .map(|((source, target), declared)| Require {
            imports: sums
                .get(&(source.as_str(), target.as_str()))
                .copied()
                .unwrap_or(0),
            source,
            target,
            rationale: declared.rationale,
            through: declared.through,
        })
        .collect()
}

/// The layers of each `layer_order` rule of the tree, in contract order.
pub(crate) fn layers(models: &ModelTree) -> Vec<LayerOrder> {
    models
        .models()
        .flat_map(|model| model.contract().rules())
        .filter_map(|rule| match rule {
            Rule::LayerOrder(order) => Some(LayerOrder {
                rule: head_of(rule).id().as_text().to_owned(),
                layers: order.layers().clone(),
            }),
            _ => None,
        })
        .collect()
}

#[cfg(test)]
#[path = "topology_declared_tests.rs"]
mod tests;
