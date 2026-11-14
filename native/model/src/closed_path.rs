// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One ordered path through a cycle (AD-484).
//!
//! A cycle of the model is a strongly connected set: its members are sorted and have no order.
//! A reader needs one closed path, `a -> b -> c -> a`. This file finds it from the links between
//! two members. The path is the shortest closed path through the first member; a tie goes to the
//! smaller name. The same links always give the same path, so a frame is stable. The path states
//! a fact of the model. It decides nothing.

use std::collections::{BTreeMap, BTreeSet, VecDeque};

/// One import between two members of a cycle: its index in the imports of the graph, and its two
/// member names.
pub type Link = (usize, String, String);

/// One step of the path: the two members and the imports that make the step.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Step {
    pub from: String,
    pub to: String,
    /// The indexes of the imports from `from` to `to`, sorted.
    pub imports: Vec<usize>,
}

/// The shortest closed path through the first member, as steps; the last step ends at the first
/// member. Empty when no member has a link that closes a path (a set that is no cycle).
pub fn cycle_path(members: &[String], links: &[Link]) -> Vec<Step> {
    let Some(start) = members.first() else {
        return Vec::new();
    };
    let mut next: BTreeMap<&str, BTreeSet<&str>> = BTreeMap::new();
    let mut by_pair: BTreeMap<(&str, &str), Vec<usize>> = BTreeMap::new();
    for (index, source, target) in links {
        if source != target {
            next.entry(source).or_default().insert(target);
            by_pair.entry((source, target)).or_default().push(*index);
        }
    }
    // A breadth-first walk from the start in name order: the first node with a link back to the
    // start ends the shortest path.
    let mut before: BTreeMap<&str, &str> = BTreeMap::new();
    let mut queue = VecDeque::from([start.as_str()]);
    let mut closing = None;
    while let Some(node) = queue.pop_front() {
        let targets = next.get(node).into_iter().flatten().copied();
        for target in targets {
            if target == start {
                closing = Some(node);
                break;
            }
            if target != start.as_str() && !before.contains_key(target) {
                before.insert(target, node);
                queue.push_back(target);
            }
        }
        if closing.is_some() {
            break;
        }
    }
    let Some(last) = closing else {
        return Vec::new();
    };
    let mut nodes = vec![last];
    while let Some(&parent) = nodes.last().and_then(|node| before.get(node)) {
        nodes.push(parent);
    }
    if nodes.last() != Some(&start.as_str()) {
        nodes.push(start);
    }
    nodes.reverse();
    nodes.push(start);
    nodes
        .windows(2)
        .map(|pair| {
            let mut imports = by_pair
                .get(&(pair[0], pair[1]))
                .cloned()
                .unwrap_or_default();
            imports.sort_unstable();
            Step {
                from: pair[0].to_owned(),
                to: pair[1].to_owned(),
                imports,
            }
        })
        .collect()
}

#[cfg(test)]
#[path = "closed_path_tests.rs"]
mod tests;
