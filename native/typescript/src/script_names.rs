// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scopes that bind each name, found once: a name is looked up by the position of a node
//! (`_script_bound_scope`).

use std::collections::HashMap;

use tree_sitter::Node;

use crate::script_scope::{Names, ScopeEntry, Tree, IN_AMBIGUOUS, NONE};

/// The last scope of the list that holds a scope that ends at `end`: the last scope, or the first
/// of its links that ends at or after `end`.
fn holder(list: &[ScopeEntry], end: usize) -> Option<usize> {
    let mut found = list.len().checked_sub(1);
    while let Some(index) = found {
        let entry = list.get(index)?;
        if end <= entry.end as usize {
            return Some(index);
        }
        found = (entry.up != NONE).then_some(entry.up as usize);
    }
    None
}

impl<'a, 't> Tree<'a, 't> {
    /// `_script_bound_scope`: the nearest ancestor that binds the name. The scopes that bind a name
    /// are a list in document order with links to the scope that holds each; the nearest ancestor
    /// is the last scope that starts before the node, or the first of its links that holds it.
    pub(crate) fn bound_scope(&self, node: Node<'t>, name: &str) -> Option<Node<'t>> {
        let at = u32::try_from(self.pos(node)?).ok()?;
        let list = self.names_index.get(name)?;
        let mut found = list
            .partition_point(|entry| entry.start < at)
            .checked_sub(1);
        while let Some(index) = found {
            let entry = list.get(index)?;
            if at < entry.end {
                return self.nodes.get(entry.scope as usize).copied();
            }
            found = (entry.up != NONE).then_some(entry.up as usize);
        }
        None
    }

    /// The scopes of the file are known: index them by name, and mark the nodes that lie inside a
    /// scope that is not statically known.
    pub(crate) fn index_scopes(&mut self) {
        let mut flags = std::mem::take(&mut self.flags);
        for (at, above) in self.parents.iter().enumerate() {
            let own = self
                .nodes
                .get(at)
                .is_some_and(|node| self.ambiguous.contains(&node.id()));
            let up = flags.get(*above as usize).copied().unwrap_or(0);
            let inherited = *above != NONE && up & IN_AMBIGUOUS != 0;
            if let Some(slot) = flags.get_mut(at).filter(|_| own || inherited) {
                *slot |= IN_AMBIGUOUS;
            }
        }
        self.flags = flags;
        let mut scopes: Vec<(usize, &Names)> = self
            .bindings
            .iter()
            .filter_map(|(id, names)| Some((*self.position.get(id)?, names)))
            .filter(|(_, names)| !names.is_empty())
            .collect();
        scopes.sort_by_key(|(at, _)| *at);
        let mut index: HashMap<String, Vec<ScopeEntry>> = HashMap::new();
        for (at, names) in scopes {
            let (start, end) = (at, self.end_of(at));
            for name in names.keys() {
                let list = index.entry(name.clone()).or_default();
                let up = holder(list, end);
                list.push(ScopeEntry {
                    start: u32::try_from(start).unwrap_or(NONE),
                    end: u32::try_from(end).unwrap_or(NONE),
                    scope: u32::try_from(at).unwrap_or(NONE),
                    up: up.map_or(NONE, |held| u32::try_from(held).unwrap_or(NONE)),
                });
            }
        }
        self.names_index = index;
    }

    /// `name in bindings.get(scope, ())`.
    pub(crate) fn binds(&self, scope: Node, name: &str) -> bool {
        self.bindings
            .get(&scope.id())
            .is_some_and(|names| names.contains_key(name))
    }

    /// `bindings[scope][name]`, zero when there is none.
    pub(crate) fn count(&self, scope: Node, name: &str) -> u32 {
        self.bindings
            .get(&scope.id())
            .and_then(|names| names.get(name))
            .copied()
            .unwrap_or(0)
    }
}
