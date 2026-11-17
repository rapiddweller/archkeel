// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Groups of the Explorer tree (AD-630, AD-794): a level never draws more boxes than one screen
//! shows. A scope with more children than `ON_SCREEN` is split by its structure: the part of the
//! names that the children share (a package prefix). A scope that no prefix splits is shown whole:
//! a cut of sorted names into ranges tells the reader nothing. A group is one more box of the tree:
//! a violated place or a gap inside it shows on the group, and the user opens it to see its
//! children, as for a component.

use std::collections::{BTreeMap, BTreeSet, HashSet};

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
    limit_counted(nodes, &mut 0);
}

/// `limit`, and the count of the boxes that it reads in `work` (#1707). The children of each box
/// are kept in one index, and only a box whose children change is checked again, so the work
/// grows with the boxes and their depth, never with their square: each round splits the first
/// scope in tree order that has too many children, as one pass over all scopes found it.
pub(super) fn limit_counted(nodes: &mut Vec<Node>, work: &mut usize) {
    let mut kids: BTreeMap<Option<usize>, Vec<usize>> = BTreeMap::new();
    for (at, n) in nodes.iter().enumerate() {
        kids.entry(n.parent).or_default().push(at);
    }
    *work += nodes.len();
    let mut ids: HashSet<String> = nodes.iter().map(|n| n.id.clone()).collect();
    let mut whole: HashSet<Option<usize>> = HashSet::new();
    let mut todo: BTreeSet<Option<usize>> = std::iter::once(None)
        .chain((0..nodes.len()).map(Some))
        .filter(|scope| crowded(nodes, &kids, *scope, work))
        .collect();
    while let Some(scope) = todo.pop_first() {
        let children = kids.get(&scope).cloned().unwrap_or_default();
        let firsts: Vec<String> = children
            .iter()
            .map(|i| first_leaf(nodes, &kids, *i, work))
            .collect();
        let labels: Vec<String> = children.iter().map(|i| nodes[*i].label.clone()).collect();
        let Some(names) = group_names(&firsts) else {
            whole.insert(scope);
            continue;
        };
        let owner = scope.map_or("ROOT".to_owned(), |s| nodes[s].id.clone());
        let mut made: Vec<(String, usize)> = Vec::new();
        // A child whose prefix no other child shares stays a box of the level: a group of one box
        // tells the reader nothing.
        let shared = |name: &String| names.iter().filter(|n| *n == name).count() >= 2;
        if !names.iter().any(shared) {
            whole.insert(scope);
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
            *work += 1;
            if !shared(name) {
                continue;
            }
            let at = match made.iter().find(|(n, _)| n == name) {
                Some((_, at)) => *at,
                None => {
                    let at = nodes.len();
                    let made_group = group(&mut ids, &owner, &label_of(name), scope, files);
                    nodes.push(made_group);
                    kids.entry(scope).or_default().push(at);
                    made.push((name.clone(), at));
                    at
                }
            };
            nodes[*child].parent = Some(at);
            kids.entry(Some(at)).or_default().push(*child);
        }
        if let Some(own) = kids.get_mut(&scope) {
            own.retain(|c| nodes[*c].parent == scope);
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
        // Only the split scope and the new groups have other children now.
        for again in std::iter::once(scope).chain(made.iter().map(|(_, at)| Some(*at))) {
            if !whole.contains(&again) && crowded(nodes, &kids, again, work) {
                todo.insert(again);
            }
        }
    }
}

/// A scope with more children than one screen shows, none of them a layer of a layer order.
fn crowded(
    nodes: &[Node],
    kids: &BTreeMap<Option<usize>, Vec<usize>>,
    scope: Option<usize>,
    work: &mut usize,
) -> bool {
    let children = kids.get(&scope).map_or(&[][..], Vec::as_slice);
    *work += 1;
    children.len() > ON_SCREEN && children.iter().all(|c| nodes[*c].rank.is_none())
}

/// The first leaf name inside a box: its own name for a component or a directory box, the first
/// name of its members for a layer or a group.
fn first_leaf(
    nodes: &[Node],
    kids: &BTreeMap<Option<usize>, Vec<usize>>,
    at: usize,
    work: &mut usize,
) -> String {
    *work += 1;
    let groups = nodes[at].rank.is_some() || nodes[at].id.starts_with("GROUP:");
    let children = if groups {
        kids.get(&Some(at)).map_or(&[][..], Vec::as_slice)
    } else {
        &[]
    };
    children
        .iter()
        .map(|i| first_leaf(nodes, kids, *i, work))
        .min()
        .unwrap_or_else(|| nodes[at].label.clone())
}

fn group(
    ids: &mut HashSet<String>,
    owner: &str,
    name: &str,
    parent: Option<usize>,
    files: bool,
) -> Node {
    // An id names one box: a name that an earlier group of the owner has gets a mark.
    let kind = if files { "FILES" } else { "GROUP" };
    let mut id = format!("{kind}:{owner}:{name}");
    while ids.contains(&id) {
        id.push('\'');
    }
    ids.insert(id.clone());
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
        // A group of directory boxes is a directory box; both are made by the report.
        directory: files,
        grouped: true,
    }
}

#[cfg(test)]
mod tests {
    use super::{limit, limit_counted, Node};

    fn node(id: &str, parent: Option<usize>) -> Node {
        Node {
            id: id.to_owned(),
            label: id.to_owned(),
            parent,
            layer: None,
            public: Vec::new(),
            path: String::new(),
            about: Vec::new(),
            forbidden: Vec::new(),
            planned: Vec::new(),
            provenance: Vec::new(),
            members: None,
            rank: None,
            directory: false,
            grouped: false,
        }
    }

    /// Two levels of name prefixes below the root (`a3.b2.m17`), and a second root box whose 40
    /// children share no prefix and stay whole.
    fn tree(leaves: usize) -> Vec<Node> {
        let mut nodes = vec![node("COMP-WIDE", None), node("COMP-FLAT", None)];
        for i in 0..leaves {
            nodes.push(node(&format!("a{}.b{}.m{i}", i % 9, i % 7), Some(0)));
        }
        for i in 0..40 {
            nodes.push(node(&format!("x{i}"), Some(1)));
        }
        nodes
    }

    /// The boxes after the split: each group with its parent and its first about line.
    fn shape(nodes: &[Node]) -> Vec<String> {
        nodes
            .iter()
            .filter(|n| n.grouped)
            .map(|n| {
                let parent = n.parent.map_or("-".to_owned(), |p| nodes[p].id.clone());
                let members = nodes
                    .iter()
                    .filter(|m| m.parent.is_some_and(|p| nodes[p].id == n.id));
                format!(
                    "{} < {parent} ({}) {}",
                    n.id,
                    members.count(),
                    n.about.join(" ")
                )
            })
            .collect()
    }

    /// FNV-1a of the listing: a stable fingerprint of the whole result.
    fn fingerprint(lines: &[String]) -> u64 {
        lines
            .join("\n")
            .bytes()
            .fold(0xcbf2_9ce4_8422_2325, |hash, byte| {
                (hash ^ u64::from(byte)).wrapping_mul(0x0100_0000_01b3)
            })
    }

    #[test]
    fn a_wide_level_is_split_by_its_prefixes_and_a_flat_one_stays_whole() {
        let mut nodes = tree(300);
        limit(&mut nodes);
        let found = shape(&nodes);
        assert!(
            found[0].starts_with("GROUP:COMP-WIDE:a0 < COMP-WIDE (7) Grouped"),
            "{found:#?}"
        );
        assert_eq!(nodes.iter().filter(|n| n.parent == Some(1)).count(), 40);
        // The golden result of the split before the work counter (#1707): the same groups, the
        // same parents and the same order.
        assert_eq!(
            (found.len(), fingerprint(&found)),
            (72, 6_030_508_755_889_822_768)
        );
    }

    /// #1707: the split of a system of 43 parts did not end in 600 s, because each round read
    /// every box once for each box. The work grows with the boxes now: twice the boxes is about
    /// twice the work, also when every level splits again.
    #[test]
    fn the_work_of_the_split_grows_with_the_boxes_and_not_with_their_square() {
        let work = |leaves: usize| {
            let mut nodes = tree(leaves);
            let mut counted = 0;
            limit_counted(&mut nodes, &mut counted);
            counted
        };
        let (small, large) = (work(4_000), work(8_000));
        assert!(large * 10 <= small * 25, "{small} -> {large}");
        assert!(small < 40 * 4_000, "{small}");
    }
}
