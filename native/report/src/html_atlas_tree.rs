// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The tree of the Explorer (AD-606): the components of the frame, and a box for each layer when
//! the top components all name a layer of the layer order. The payload and its levels read it.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;

pub(super) use super::atlas_node::Node;
use super::frame::{Component, Frame, Topology};
use crate::head::RuleVerdict;

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

/// The components as a tree, the component that owns each module, and the box that shows it.
pub(super) struct Tree {
    pub(super) nodes: Vec<Node>,
    /// The component of the contract that owns each module: its assignment says this owner.
    pub(super) owner: BTreeMap<String, usize>,
    /// The box that shows each module on the map: its owner, or a directory box inside the owner
    /// when the owner has more modules than one screen shows.
    pub(super) place: BTreeMap<String, usize>,
    /// The languages of the modules inside each node, from the collector of each module.
    pub(super) languages: Vec<BTreeSet<String>>,
}

/// A scope (the top of the tree, or one part of a system) whose children all name a layer of one
/// layer order, with that order.
type Group<'a> = (Option<&'a str>, &'a [String]);

fn layer_id(scope: Option<&str>, layer: &str) -> String {
    match scope {
        None => format!("LAYER:{layer}"),
        Some(part) => format!("LAYER:{part}:{layer}"),
    }
}

/// The scopes whose children are drawn by layer first (AD-606, AD-618).
fn grouped_scopes(topology: &Topology) -> Vec<Group<'_>> {
    let scopes = std::iter::once(None).chain(
        topology
            .components
            .iter()
            .filter(|c| c.parent.is_none() && c.layer.is_none())
            .map(|c| Some(c.id.as_str())),
    );
    let mut grouped = Vec::new();
    for scope in scopes {
        let children: Vec<_> = topology
            .components
            .iter()
            .filter(|c| c.parent.as_deref() == scope)
            .collect();
        let order = topology.layers.iter().find(|o| {
            o.part.as_deref() == scope
                && !children.is_empty()
                && children
                    .iter()
                    .all(|c| c.layer.as_ref().is_some_and(|l| o.layers.contains(l)))
        });
        if let Some(order) = order {
            grouped.push((scope, order.layers.as_slice()));
        }
    }
    grouped
}

/// One box for each layer of each grouped scope, without a parent yet.
fn layer_nodes(topology: &Topology, grouped: &[Group<'_>]) -> Vec<Node> {
    let mut nodes = Vec::new();
    for (scope, order) in grouped {
        for (step, layer) in order.iter().enumerate() {
            let members: Vec<&str> = topology
                .components
                .iter()
                .filter(|c| c.parent.as_deref() == *scope && c.layer.as_ref() == Some(layer))
                .map(|c| c.name.as_str())
                .collect();
            nodes.push(Node {
                id: layer_id(*scope, layer),
                label: layer.clone(),
                parent: None,
                layer: Some(layer.clone()),
                public: Vec::new(),
                path: format!("layer {layer}"),
                about: vec![format!(
                    "Layer {} of {}: {}.",
                    step + 1,
                    order.len(),
                    members.join(", ")
                )],
                forbidden: Vec::new(),
                planned: Vec::new(),
                provenance: Vec::new(),
                members: None,
                rank: Some(step),
                directory: false,
                grouped: false,
            });
        }
    }
    nodes
}

/// The word that `init` drafts for a text that nobody has written yet.
pub(super) const DRAFT_WORD: &str = "TODO";

/// A text of the contract as the page shows it: a drafted `TODO` is a text that is not written yet,
/// not a defect of the page.
fn written(text: &str, what: &str) -> String {
    if text.trim().starts_with(DRAFT_WORD) {
        format!("{what} not written yet.")
    } else {
        text.to_owned()
    }
}

/// The box of one component under `parent`.
fn component_node(component: &Component, parent: Option<usize>) -> Node {
    Node {
        id: component.id.clone(),
        label: component.name.clone(),
        parent,
        layer: component.layer.clone(),
        public: component.public.clone(),
        path: component.packages.join(", "),
        about: component
            .responsibilities
            .iter()
            .map(|t| written(t, "Responsibility"))
            .collect(),
        forbidden: component
            .forbidden_responsibilities
            .iter()
            .map(|t| written(t, "Boundary"))
            .collect(),
        planned: component.planned_public.clone(),
        provenance: component.provenance.clone(),
        members: None,
        rank: None,
        directory: false,
        grouped: false,
    }
}

impl Tree {
    /// The children of a scope are drawn by layer first when each of them names a layer of one
    /// layer order: each layer is one box above its components (AD-606, AD-618).
    pub(super) fn of(topology: &Topology) -> Tree {
        let grouped = grouped_scopes(topology);
        let mut nodes = layer_nodes(topology, &grouped);
        let first = nodes.len();
        let index: BTreeMap<&str, usize> = topology
            .components
            .iter()
            .enumerate()
            .map(|(i, c)| (c.id.as_str(), first + i))
            .collect();
        // A layer box sits inside the part that it orders.
        for node in &mut nodes {
            let part = grouped.iter().find_map(|(scope, _)| {
                let scope = (*scope)?;
                node.id
                    .starts_with(&format!("LAYER:{scope}:"))
                    .then_some(scope)
            });
            node.parent = part.and_then(|part| index.get(part).copied());
        }
        for component in &topology.components {
            let scope_grouped = grouped
                .iter()
                .any(|(s, _)| *s == component.parent.as_deref());
            let parent = match (&component.parent, &component.layer) {
                (parent, Some(layer)) if scope_grouped => {
                    let id = layer_id(parent.as_deref(), layer);
                    nodes.iter().position(|n| n.id == id)
                }
                (Some(parent), _) => index.get(parent.as_str()).copied(),
                (None, _) => None,
            };
            nodes.push(component_node(component, parent));
        }
        // Before the groups: many directory boxes of one component are grouped by their path
        // prefix. A component is grouped by its own name, never by the names of its boxes.
        let directories = super::atlas_dirs::split(&mut nodes, topology, &index);
        super::atlas_groups::limit(&mut nodes);
        super::atlas_members::aggregate(&mut nodes);
        let owner: BTreeMap<String, usize> = topology
            .modules
            .iter()
            .filter_map(|m| Some((m.name.clone(), *index.get(m.component.as_deref()?)?)))
            .collect();
        let mut place = owner.clone();
        place.extend(directories);
        let mut tree = Tree {
            languages: vec![BTreeSet::new(); nodes.len()],
            nodes,
            owner,
            place,
        };
        for module in topology.modules.iter().filter(|m| !m.language.is_empty()) {
            let Some(owner) = tree.place.get(&module.name).copied() else {
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
        .filter(|(_, row)| row.1 == RuleVerdict::Unknown)
        .filter_map(|(rule, _)| frame.explain.holds.rules.get(rule))
        .flat_map(|hold| &hold.pairs)
        .map(|p| (p.source.clone(), p.target.clone()))
        .collect()
}
