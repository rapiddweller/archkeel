// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The strongly connected components of a graph and the ranks of its condensation (slice S3).
//!
//! Reference engine: `ir/graph.py` `strongly_connected_components` and `condensation_ranks`.
//! A node is an index in name order. The members of a component are sorted, so the members
//! do not depend on the order of the walk. A rank is the length of the longest path from a
//! component without a predecessor to the component of the node: the reference engine sorts its
//! queue, but each order of a topological walk gives the same longest path, so no tie break
//! changes a rank.
//!
//! The walk uses an explicit stack, never recursion: the depth of the input graph does not
//! touch the depth of the call stack.

/// The components and the ranks of one graph.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Condensation {
    component: Vec<usize>,
    members: Vec<Vec<usize>>,
    rank: Vec<usize>,
}

impl Condensation {
    /// The rank of a node, or 0 for an index outside the graph (`ranks.get(node, 0)`).
    pub(crate) fn rank(&self, node: usize) -> usize {
        self.component
            .get(node)
            .and_then(|component| self.rank.get(*component))
            .copied()
            .unwrap_or(0)
    }

    /// The members of each component, each sorted, in the order of the walk.
    pub(crate) fn components(&self) -> &[Vec<usize>] {
        &self.members
    }
}

/// The condensation of the nodes `0..count` and the edges. An edge with an end outside the
/// nodes is ignored, as the reference engine ignores an edge to a node that it does not list.
pub(crate) fn condense(count: usize, edges: &[(usize, usize)]) -> Condensation {
    let edges: Vec<(usize, usize)> = edges
        .iter()
        .copied()
        .filter(|&(source, target)| source < count && target < count)
        .collect();
    let successors = adjacency(count, edges.iter().copied());
    let (component, members) = components(&successors);
    let rank = ranks(&component, members.len(), &edges);
    Condensation {
        component,
        members,
        rank,
    }
}

/// The successors of each node, in compressed rows: `starts[n]..starts[n + 1]` in `targets`.
struct Adjacency {
    starts: Vec<usize>,
    targets: Vec<usize>,
}

impl Adjacency {
    fn of(&self, node: usize) -> &[usize] {
        let start = self.starts.get(node).copied().unwrap_or(0);
        let end = self.starts.get(node + 1).copied().unwrap_or(start);
        self.targets.get(start..end).unwrap_or(&[])
    }
}

fn adjacency(count: usize, edges: impl Iterator<Item = (usize, usize)> + Clone) -> Adjacency {
    let mut starts = vec![0; count + 1];
    for (source, _) in edges.clone() {
        starts[source + 1] += 1;
    }
    for node in 0..count {
        starts[node + 1] += starts[node];
    }
    let mut next = starts.clone();
    let mut targets = vec![0; starts[count]];
    for (source, target) in edges {
        targets[next[source]] = target;
        next[source] += 1;
    }
    Adjacency { starts, targets }
}

const UNSEEN: usize = usize::MAX;

/// Tarjan's components with an explicit stack: the component of each node and the sorted
/// members of each component.
fn components(successors: &Adjacency) -> (Vec<usize>, Vec<Vec<usize>>) {
    let count = successors.starts.len().saturating_sub(1);
    let mut walk = Walk {
        order: vec![UNSEEN; count],
        low: vec![0; count],
        on_stack: vec![false; count],
        component: vec![0; count],
        members: Vec::new(),
        stack: Vec::new(),
        calls: Vec::new(),
        seen: 0,
    };
    for root in 0..count {
        if walk.order[root] == UNSEEN {
            walk.enter(root);
            while walk.step(successors) {}
        }
    }
    (walk.component, walk.members)
}

/// The state of one walk of Tarjan's algorithm. `calls` holds each open node and the position
/// of its next successor: it replaces the call stack of a recursive walk.
struct Walk {
    order: Vec<usize>,
    low: Vec<usize>,
    on_stack: Vec<bool>,
    component: Vec<usize>,
    members: Vec<Vec<usize>>,
    stack: Vec<usize>,
    calls: Vec<(usize, usize)>,
    seen: usize,
}

impl Walk {
    fn enter(&mut self, node: usize) {
        self.order[node] = self.seen;
        self.low[node] = self.seen;
        self.seen += 1;
        self.stack.push(node);
        self.on_stack[node] = true;
        self.calls.push((node, 0));
    }

    /// One step: follow the next successor of the open node, or close the node. False when no
    /// node is open.
    fn step(&mut self, successors: &Adjacency) -> bool {
        let Some(call) = self.calls.last_mut() else {
            return false;
        };
        let (node, position) = *call;
        call.1 += 1;
        match successors.of(node).get(position) {
            Some(&next) if self.order[next] == UNSEEN => self.enter(next),
            Some(&next) if self.on_stack[next] => {
                self.low[node] = self.low[node].min(self.order[next]);
            }
            Some(_) => {}
            None => self.close(node),
        }
        true
    }

    fn close(&mut self, node: usize) {
        self.calls.pop();
        if let Some(&(parent, _)) = self.calls.last() {
            self.low[parent] = self.low[parent].min(self.low[node]);
        }
        if self.low[node] == self.order[node] {
            let found = pop_component(&mut self.stack, &mut self.on_stack, node);
            for &member in &found {
                self.component[member] = self.members.len();
            }
            self.members.push(found);
        }
    }
}

/// Pop the members of the component of `root` from the stack, sorted.
fn pop_component(stack: &mut Vec<usize>, on_stack: &mut [bool], root: usize) -> Vec<usize> {
    let mut found = Vec::new();
    while let Some(member) = stack.pop() {
        on_stack[member] = false;
        found.push(member);
        if member == root {
            break;
        }
    }
    found.sort_unstable();
    found
}

/// The longest path to each component in the graph of the components (Kahn's walk).
fn ranks(component: &[usize], count: usize, edges: &[(usize, usize)]) -> Vec<usize> {
    let mut links: Vec<(usize, usize)> = edges
        .iter()
        .map(|&(source, target)| (component[source], component[target]))
        .filter(|(source, target)| source != target)
        .collect();
    links.sort_unstable();
    links.dedup();
    let successors = adjacency(count, links.iter().copied());
    let mut waiting = vec![0usize; count];
    for &(_, target) in &links {
        waiting[target] += 1;
    }
    let mut rank = vec![0; count];
    let mut ready: Vec<usize> = (0..count).filter(|&node| waiting[node] == 0).collect();
    while let Some(current) = ready.pop() {
        for &target in successors.of(current) {
            rank[target] = rank[target].max(rank[current] + 1);
            waiting[target] -= 1;
            if waiting[target] == 0 {
                ready.push(target);
            }
        }
    }
    rank
}

#[cfg(test)]
#[path = "condensation_tests.rs"]
mod tests;
