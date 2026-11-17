// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Groups of the Explorer tree (AD-630): a level never draws more boxes than stay readable. A scope
//! with more children than `READABLE` is split into groups named by the part of the names that the
//! children share (a package prefix), or, when no prefix splits them, by ranges of the sorted names.
//! A group is one more box of the tree: a violated place or a gap inside it shows on the group, and
//! the user opens it to see its children, as for a component.

use super::atlas_node::Node;

/// The most boxes of one level of the Explorer: a level up to this size is drawn as it is, and a
/// larger one is split into groups (lead decision of the second UX test: about twelve).
pub(super) const READABLE: usize = 12;

/// The most boxes of one range group: a group is opened to be read, so it stays small.
const RANGE: usize = 6;

/// The name of the group of each span `(first, last)` of leaf names: the first `depth` segments of
/// the first name when that gives between two and `READABLE` groups, else ranges of `RANGE`
/// sorted spans (a set of more than `READABLE` ranges is grouped again). A range names the first
/// and the last leaf, so a group of groups has a short name too.
pub(super) fn group_names(spans: &[(String, String)]) -> (Vec<String>, bool) {
    let labels: Vec<&str> = spans.iter().map(|(first, _)| first.as_str()).collect();
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
            if (2..=READABLE).contains(&distinct.len()) {
                return (keys, true);
            }
        }
    }
    // Balanced ranges: `ceil(n / RANGE)` groups whose sizes differ by at most one, so no range
    // holds a single box (a range of one box would carry the name of that box).
    let mut order: Vec<usize> = (0..labels.len()).collect();
    order.sort_by_key(|i| labels[*i]);
    let groups = labels.len().div_ceil(RANGE);
    let (base, extra) = (labels.len() / groups, labels.len() % groups);
    let mut names = vec![String::new(); labels.len()];
    let mut start = 0;
    for group in 0..groups {
        let end = start + base + usize::from(group < extra);
        let chunk = &order[start..end];
        let last = chunk
            .iter()
            .map(|i| spans[*i].1.as_str())
            .max()
            .unwrap_or_default();
        let name = format!("{} to {last}", labels[chunk[0]]);
        for i in chunk {
            names[*i].clone_from(&name);
        }
        start = end;
    }
    (names, false)
}

/// Split each scope that has more than `READABLE` children into groups, until none has.
pub(super) fn limit(nodes: &mut Vec<Node>) {
    loop {
        // The boxes of a layer order stay together: the order is the picture that the contract
        // draws, and a layer holds its components.
        let mut scopes: Vec<Option<usize>> = std::iter::once(None)
            .chain((0..nodes.len()).map(Some))
            .collect();
        scopes.retain(|scope| {
            let kids: Vec<&Node> = nodes.iter().filter(|n| n.parent == *scope).collect();
            kids.len() > READABLE && kids.iter().all(|n| n.rank.is_none())
        });
        let Some(scope) = scopes.first().copied() else {
            return;
        };
        let children: Vec<usize> = (0..nodes.len())
            .filter(|i| nodes[*i].parent == scope)
            .collect();
        let spans: Vec<(String, String)> = children.iter().map(|i| span(nodes, *i)).collect();
        let labels: Vec<String> = children.iter().map(|i| nodes[*i].label.clone()).collect();
        let (names, by_prefix) = group_names(&spans);
        let owner = scope.map_or("ROOT".to_owned(), |s| nodes[s].id.clone());
        let mut made: Vec<(String, usize)> = Vec::new();
        for (child, name) in children.iter().zip(&names) {
            let at = match made.iter().find(|(n, _)| n == name) {
                Some((_, at)) => *at,
                None => {
                    let at = nodes.len();
                    let made_group = group(nodes, &owner, name, scope);
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
            let why = if by_prefix {
                format!(
                    "Grouped by the name prefix `{name}`: this level has {} boxes, more than {READABLE}.",
                    children.len()
                )
            } else {
                format!(
                    "Grouped by size: this level has {} boxes, more than {READABLE}; the names are sorted and cut into ranges.",
                    children.len()
                )
            };
            nodes[*at].about = vec![why, format!("{} boxes: {shown}{more}.", members.len())];
        }
    }
}

/// The first and the last leaf name inside a box: its own name for a component.
fn span(nodes: &[Node], at: usize) -> (String, String) {
    let kids: Vec<(String, String)> = (0..nodes.len())
        .filter(|i| nodes[*i].parent == Some(at))
        .map(|i| span(nodes, i))
        .collect();
    let first = kids.iter().map(|(f, _)| f.clone()).min();
    let last = kids.iter().map(|(_, l)| l.clone()).max();
    match (first, last) {
        (Some(first), Some(last)) => (first, last),
        _ => (nodes[at].label.clone(), nodes[at].label.clone()),
    }
}

fn group(nodes: &[Node], owner: &str, name: &str, parent: Option<usize>) -> Node {
    // An id names one box: a name that an earlier group of the owner has gets a mark.
    let mut id = format!("GROUP:{owner}:{name}");
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
        directory: false,
    }
}
