// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Groups of the Explorer tree (AD-630, AD-794): a level never draws more boxes than one screen
//! shows. A scope with more children than `ON_SCREEN` is split by its structure: the part of the
//! names that the children share (a package prefix). A scope that no prefix splits is shown whole:
//! a cut of sorted names into ranges tells the reader nothing. A group is one more box of the tree:
//! a violated place or a gap inside it shows on the group, and the user opens it to see its
//! children, as for a component.

use super::atlas_node::{Node, ON_SCREEN};

/// The group name of each leaf name: the first `depth` segments of the name at the first separator
/// and depth that give between two and `ON_SCREEN` groups; `None` when no prefix splits the names.
pub(super) fn group_names(labels: &[String]) -> Option<Vec<String>> {
    for separator in ['.', '/', ':', '_', '-'] {
        for depth in 1..=4 {
            let keys: Vec<String> = labels
                .iter()
                .map(|label| {
                    let parts: Vec<&str> = label.split(separator).collect();
                    parts[..depth.min(parts.len())].join(&separator.to_string())
                })
                .collect();
            let distinct: std::collections::BTreeSet<&String> = keys.iter().collect();
            if (2..=ON_SCREEN).contains(&distinct.len()) && distinct.len() < labels.len() {
                return Some(keys);
            }
        }
    }
    None
}

/// Split each scope that has more than `ON_SCREEN` children into groups by a shared prefix, until
/// none has or no prefix splits the rest.
pub(super) fn limit(nodes: &mut Vec<Node>) {
    let mut whole: Vec<Option<usize>> = Vec::new();
    loop {
        // The boxes of a layer order stay together: the order is the picture that the contract
        // draws, and a layer holds its components.
        let mut scopes: Vec<Option<usize>> = std::iter::once(None)
            .chain((0..nodes.len()).map(Some))
            .collect();
        scopes.retain(|scope| {
            let kids: Vec<&Node> = nodes.iter().filter(|n| n.parent == *scope).collect();
            kids.len() > ON_SCREEN
                && kids.iter().all(|n| n.rank.is_none())
                && !whole.contains(scope)
        });
        let Some(scope) = scopes.first().copied() else {
            return;
        };
        let children: Vec<usize> = (0..nodes.len())
            .filter(|i| nodes[*i].parent == scope)
            .collect();
        let firsts: Vec<String> = children.iter().map(|i| first_leaf(nodes, *i)).collect();
        let labels: Vec<String> = children.iter().map(|i| nodes[*i].label.clone()).collect();
        let Some(names) = group_names(&firsts) else {
            whole.push(scope);
            continue;
        };
        let owner = scope.map_or("ROOT".to_owned(), |s| nodes[s].id.clone());
        let mut made: Vec<(String, usize)> = Vec::new();
        // A child whose prefix no other child shares stays a box of the level: a group of one box
        // tells the reader nothing.
        let shared = |name: &String| names.iter().filter(|n| *n == name).count() >= 2;
        if !names.iter().any(shared) {
            whole.push(scope);
            continue;
        }
        // A group of directory boxes is a directory box of the path prefix.
        let files = children.iter().all(|c| nodes[*c].directory);
        let label_of = |name: &String| {
            if files {
                format!("{name}/")
            } else {
                name.clone()
            }
        };
        for (child, name) in children.iter().zip(&names) {
            if !shared(name) {
                continue;
            }
            let at = match made.iter().find(|(n, _)| n == name) {
                Some((_, at)) => *at,
                None => {
                    let at = nodes.len();
                    let made_group = group(nodes, &owner, &label_of(name), scope, files);
                    nodes.push(made_group);
                    made.push((name.clone(), at));
                    at
                }
            };
            nodes[*child].parent = Some(at);
        }
        for (name, at) in &made {
            let members: Vec<&str> = names
                .iter()
                .zip(&labels)
                .filter(|(n, _)| *n == name)
                .map(|(_, label)| label.as_str())
                .collect();
            let shown = members
                .iter()
                .take(3)
                .copied()
                .collect::<Vec<_>>()
                .join(", ");
            let more = if members.len() > 3 { ", ..." } else { "" };
            // A group says why it is a group (a level of this size is split), and what is in it.
            let why = format!(
                "Grouped by the name prefix `{name}`: this level has {} boxes, more than one screen shows ({ON_SCREEN}).",
                children.len()
            );
            nodes[*at].about = vec![why, format!("{} boxes: {shown}{more}.", members.len())];
        }
    }
}

/// The first leaf name inside a box: its own name for a component or a directory box, the first
/// name of its members for a layer or a group.
fn first_leaf(nodes: &[Node], at: usize) -> String {
    let groups = nodes[at].rank.is_some() || nodes[at].id.starts_with("GROUP:");
    (0..nodes.len())
        .filter(|i| groups && nodes[*i].parent == Some(at))
        .map(|i| first_leaf(nodes, i))
        .min()
        .unwrap_or_else(|| nodes[at].label.clone())
}

fn group(nodes: &[Node], owner: &str, name: &str, parent: Option<usize>, files: bool) -> Node {
    // An id names one box: a name that an earlier group of the owner has gets a mark.
    let kind = if files { "FILES" } else { "GROUP" };
    let mut id = format!("{kind}:{owner}:{name}");
    while nodes.iter().any(|n| n.id == id) {
        id.push('\'');
    }
    Node {
        id,
        label: name.to_owned(),
        parent,
        layer: None,
        public: Vec::new(),
        path: format!("group {name}"),
        about: Vec::new(),
        forbidden: Vec::new(),
        planned: Vec::new(),
        provenance: Vec::new(),
        members: None,
        rank: None,
        directory: files,
    }
}
