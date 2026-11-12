// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The components and ranks of slice S3 (`strongly_connected_components`, `condensation_ranks`).

use std::collections::{BTreeMap, BTreeSet};

use super::{condense, Condensation};

fn ranks(condensation: &Condensation, count: usize) -> Vec<usize> {
    (0..count).map(|node| condensation.rank(node)).collect()
}

fn sorted_components(condensation: &Condensation) -> Vec<Vec<usize>> {
    let mut found = condensation.components().to_vec();
    found.sort();
    found
}

#[test]
fn a_chain_ranks_each_node_one_above_its_source() {
    let found = condense(4, &[(0, 1), (1, 2), (2, 3)]);
    assert_eq!(ranks(&found, 4), vec![0, 1, 2, 3]);
}

#[test]
fn a_node_takes_the_longest_path_and_not_the_shortest() {
    // 0 -> 3 directly and 0 -> 1 -> 2 -> 3: the rank of 3 is 3, not 1.
    let found = condense(4, &[(0, 3), (0, 1), (1, 2), (2, 3)]);
    assert_eq!(ranks(&found, 4), vec![0, 1, 2, 3]);
}

#[test]
fn the_members_of_a_cycle_share_one_rank_and_one_sorted_component() {
    // 0 -> 1 -> 2 -> 1 and 2 -> 3: {1, 2} is one component of rank 1, and 3 has rank 2.
    let found = condense(4, &[(0, 1), (1, 2), (2, 1), (2, 3)]);
    assert_eq!(ranks(&found, 4), vec![0, 1, 1, 2]);
    assert_eq!(
        sorted_components(&found),
        vec![vec![0], vec![1, 2], vec![3]]
    );
}

#[test]
fn a_cycle_that_closes_late_keeps_its_members_sorted() {
    // The walk reaches 3 before it closes 3 -> 0: the members are still in index order.
    let found = condense(4, &[(0, 3), (3, 1), (1, 2), (2, 0)]);
    assert_eq!(sorted_components(&found), vec![vec![0, 1, 2, 3]]);
    assert_eq!(ranks(&found, 4), vec![0, 0, 0, 0]);
}

#[test]
fn a_self_edge_a_repeated_edge_and_an_edge_outside_the_nodes_change_no_rank() {
    let found = condense(3, &[(0, 0), (0, 1), (0, 1), (1, 7), (9, 2)]);
    assert_eq!(ranks(&found, 3), vec![0, 1, 0]);
    assert_eq!(found.rank(7), 0);
    assert_eq!(sorted_components(&found), vec![vec![0], vec![1], vec![2]]);
}

#[test]
fn disconnected_parts_rank_on_their_own() {
    let found = condense(5, &[(3, 4), (0, 1)]);
    assert_eq!(ranks(&found, 5), vec![0, 1, 0, 0, 1]);
    assert_eq!(condense(0, &[]).components().len(), 0);
}

#[test]
fn a_chain_of_100_000_nodes_needs_no_recursion() {
    let count = 100_000;
    let edges: Vec<(usize, usize)> = (1..count).map(|node| (node - 1, node)).collect();
    let found = condense(count, &edges);
    assert_eq!(found.rank(count - 1), count - 1);
    assert_eq!(found.components().len(), count);
    // The reverse chain: the walk from node 0 sees no successor, and each later root is deep.
    let reverse: Vec<(usize, usize)> = (1..count).map(|node| (node, node - 1)).collect();
    assert_eq!(condense(count, &reverse).rank(0), count - 1);
}

#[test]
fn one_cycle_of_100_000_nodes_is_one_component_of_rank_0() {
    let count = 100_000;
    let mut edges: Vec<(usize, usize)> = (1..count).map(|node| (node - 1, node)).collect();
    edges.push((count - 1, 0));
    let found = condense(count, &edges);
    assert_eq!(found.components().len(), 1);
    assert_eq!(found.components()[0].len(), count);
    assert!(found.components()[0]
        .windows(2)
        .all(|pair| pair[0] < pair[1]));
    assert_eq!(found.rank(count / 2), 0);
}

/// The reference engine, written as it is (`ir/graph.py`): recursive Kosaraju over sorted
/// adjacency, and Kahn's walk over a sorted queue.
fn reference(count: usize, edges: &[(usize, usize)]) -> (Vec<Vec<usize>>, Vec<usize>) {
    let pairs: BTreeSet<(usize, usize)> = edges.iter().copied().collect();
    let mut forward: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); count];
    let mut reverse: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); count];
    for &(source, target) in &pairs {
        forward[source].insert(target);
        reverse[target].insert(source);
    }
    fn visit(node: usize, next: &[BTreeSet<usize>], seen: &mut [bool], out: &mut Vec<usize>) {
        seen[node] = true;
        for &target in &next[node] {
            if !seen[target] {
                visit(target, next, seen, out);
            }
        }
        out.push(node);
    }
    let mut seen = vec![false; count];
    let mut order = Vec::new();
    for node in 0..count {
        if !seen[node] {
            visit(node, &forward, &mut seen, &mut order);
        }
    }
    let mut seen = vec![false; count];
    let mut components: Vec<Vec<usize>> = Vec::new();
    for &node in order.iter().rev() {
        if !seen[node] {
            let mut component = Vec::new();
            visit(node, &reverse, &mut seen, &mut component);
            component.sort_unstable();
            components.push(component);
        }
    }
    components.sort_by_key(|component| (component[0], component.len()));
    let index: BTreeMap<usize, usize> = components
        .iter()
        .enumerate()
        .flat_map(|(at, members)| members.iter().map(move |&member| (member, at)))
        .collect();
    let mut predecessors: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); components.len()];
    let mut successors: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); components.len()];
    for &(source, target) in &pairs {
        let (from, to) = (index[&source], index[&target]);
        if from != to {
            successors[from].insert(to);
            predecessors[to].insert(from);
        }
    }
    let mut ready: Vec<usize> = (0..components.len())
        .filter(|&at| predecessors[at].is_empty())
        .collect();
    let mut rank: BTreeMap<usize, usize> = ready.iter().map(|&at| (at, 0)).collect();
    while !ready.is_empty() {
        let current = ready.remove(0);
        for &target in &successors[current].clone() {
            let value = rank
                .get(&target)
                .copied()
                .unwrap_or(0)
                .max(rank[&current] + 1);
            rank.insert(target, value);
            predecessors[target].remove(&current);
            if predecessors[target].is_empty() && !ready.contains(&target) {
                ready.push(target);
                ready.sort_unstable();
            }
        }
    }
    let ranks = (0..count)
        .map(|node| rank.get(&index[&node]).copied().unwrap_or(0))
        .collect();
    (components, ranks)
}

#[test]
fn each_graph_of_a_seeded_set_has_the_components_and_ranks_of_the_reference_engine() {
    let mut state: u64 = 0x5eed;
    let mut next = |bound: u64| {
        state = state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        usize::try_from((state >> 33) % bound).unwrap()
    };
    for _ in 0..500 {
        let count = 1 + next(12);
        let edge_count = next(30);
        let edges: Vec<(usize, usize)> = (0..edge_count)
            .map(|_| (next(count as u64), next(count as u64)))
            .collect();
        let found = condense(count, &edges);
        let (components, expected) = reference(count, &edges);
        assert_eq!(ranks(&found, count), expected, "edges {edges:?}");
        assert_eq!(sorted_components(&found), components, "edges {edges:?}");
    }
}
