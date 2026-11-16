// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The tree of the Explorer (AD-606): the components of the frame, and a box for each layer when
//! the top components all name a layer of the layer order. The payload and its levels read it.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

use super::frame::{Frame, Topology};

/// The texts that the payload names by index.
#[derive(Default)]
pub(super) struct Refs {
    pub(super) list: Vec<String>,
    index: BTreeMap<String, usize>,
}

impl Refs {
    pub(super) fn id(&mut self, text: &str) -> usize {
        if let Some(found) = self.index.get(text) {
            return *found;
        }
        self.list.push(text.to_owned());
        self.index.insert(text.to_owned(), self.list.len() - 1);
        self.list.len() - 1
    }
}

/// One box of the Explorer: a component of the contract, or a layer of its layer order.
pub(super) struct Node {
    pub(super) id: String,
    pub(super) label: String,
    pub(super) parent: Option<usize>,
    pub(super) layer: Option<String>,
    pub(super) public: Vec<String>,
    pub(super) path: String,
    /// What the box is responsible for; a layer names the count of its components.
    pub(super) about: Vec<String>,
    /// What the component must not do, and its planned surface, as the contract states them.
    pub(super) forbidden: Vec<String>,
    pub(super) planned: Vec<String>,
    /// The place of a layer in its layer order, from the inner layer; `None` for a component.
    pub(super) rank: Option<usize>,
}

/// The components as a tree, and the component that owns each module.
pub(super) struct Tree {
    pub(super) nodes: Vec<Node>,
    pub(super) owner: BTreeMap<String, usize>,
    /// The languages of the modules inside each node, from the collector of each module.
    pub(super) languages: Vec<BTreeSet<String>>,
}

impl Tree {
    /// A contract whose top components all name a layer of its first layer order is drawn by
    /// layer first: each layer is one box above its components.
    pub(super) fn of(topology: &Topology) -> Tree {
        let order = topology.layers.first().map(|o| &o.layers);
        let tops: Vec<_> = topology
            .components
            .iter()
            .filter(|c| c.parent.is_none())
            .collect();
        let grouped = order.is_some_and(|layers| {
            !tops.is_empty()
                && tops
                    .iter()
                    .all(|c| c.layer.as_ref().is_some_and(|l| layers.contains(l)))
        });
        let mut nodes: Vec<Node> = Vec::new();
        if grouped {
            for (step, layer) in order.into_iter().flatten().enumerate() {
                let members: Vec<&str> = tops
                    .iter()
                    .filter(|c| c.layer.as_ref() == Some(layer))
                    .map(|c| c.name.as_str())
                    .collect();
                nodes.push(Node {
                    id: format!("LAYER:{layer}"),
                    label: layer.clone(),
                    parent: None,
                    layer: Some(layer.clone()),
                    public: Vec::new(),
                    path: format!("layer {layer}"),
                    about: vec![format!(
                        "Layer {} of {}: {}.",
                        step + 1,
                        order.map_or(0, Vec::len),
                        members.join(", ")
                    )],
                    forbidden: Vec::new(),
                    planned: Vec::new(),
                    rank: Some(step),
                });
            }
        }
        let first = nodes.len();
        let index: BTreeMap<&str, usize> = topology
            .components
            .iter()
            .enumerate()
            .map(|(i, c)| (c.id.as_str(), first + i))
            .collect();
        for component in &topology.components {
            let parent = match &component.parent {
                Some(parent) => index.get(parent.as_str()).copied(),
                None if grouped => component
                    .layer
                    .as_ref()
                    .and_then(|l| nodes.iter().position(|n| n.id == format!("LAYER:{l}"))),
                None => None,
            };
            nodes.push(Node {
                id: component.id.clone(),
                label: component.name.clone(),
                parent,
                layer: component.layer.clone(),
                public: component.public.clone(),
                path: component.packages.join(", "),
                about: component.responsibilities.clone(),
                forbidden: component.forbidden_responsibilities.clone(),
                planned: component.planned_public.clone(),
                rank: None,
            });
        }
        let owner: BTreeMap<String, usize> = topology
            .modules
            .iter()
            .filter_map(|m| Some((m.name.clone(), *index.get(m.component.as_deref()?)?)))
            .collect();
        let mut tree = Tree {
            languages: vec![BTreeSet::new(); nodes.len()],
            nodes,
            owner,
        };
        for module in topology.modules.iter().filter(|m| !m.language.is_empty()) {
            let Some(owner) = tree.owner.get(&module.name).copied() else {
                continue;
            };
            for node in tree.chain(owner).collect::<Vec<_>>() {
                tree.languages[node].insert(module.language.clone());
            }
        }
        tree
    }

    /// The node and each of its ancestors, from the node up.
    pub(super) fn chain(&self, node: usize) -> impl Iterator<Item = usize> + '_ {
        std::iter::successors(Some(node), |i| self.nodes[*i].parent)
    }

    /// The child of `level` that holds `node`, or `None` when the node is outside the level.
    pub(super) fn child_under(&self, level: Option<usize>, node: usize) -> Option<usize> {
        self.chain(node).find(|i| self.nodes[*i].parent == level)
    }

    pub(super) fn inside(&self, level: Option<usize>, node: usize) -> bool {
        level.is_none_or(|l| self.chain(node).any(|i| i == l))
    }
}

/// One violated place, with the modules that it names.
pub(super) struct Finding {
    pub(super) value: Value,
    pub(super) modules: Vec<String>,
    pub(super) pair: Option<(String, String)>,
}

/// The pairs of modules that a gap holds for an UNKNOWN rule.
pub(super) fn held(frame: &Frame) -> BTreeSet<(String, String)> {
    frame
        .rules
        .iter()
        .filter(|(_, row)| row.1 == "UNKNOWN")
        .filter_map(|(rule, _)| frame.explain.holds.rules.get(rule))
        .flat_map(|hold| &hold.pairs)
        .map(|p| (p.source.clone(), p.target.clone()))
        .collect()
}
