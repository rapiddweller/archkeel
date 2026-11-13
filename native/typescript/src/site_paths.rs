// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Static paths (`_static_path`) and the texts of a site, kept as byte ranges.
//!
//! `a.b.c.d` gives the path of each member of the chain, and a path is as long as its chain. A site
//! that held its path as a list of names would cost the square of the chain. Here a path is an item
//! of an arena that points at the item of its receiver, so a chain of n members costs n items, and
//! the names are cut from the source only when a reader asks for them.

use std::collections::HashMap;

use tree_sitter::Node;

use crate::kinds::K;
use crate::pytext::decode;
use crate::tree::cx::Cx;

/// A range of bytes of the file: the text of a node, decoded only when it is read.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct Text {
    pub start: usize,
    pub end: usize,
}

impl Text {
    pub(crate) fn of(node: Node) -> Self {
        Self {
            start: node.start_byte(),
            end: node.end_byte(),
        }
    }

    /// `not text`: a node of no bytes.
    pub(crate) fn is_empty(self) -> bool {
        self.start >= self.end
    }

    /// `str(data[start:end], "utf-8", "replace")`.
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    pub(crate) fn decode(self, data: &[u8]) -> String {
        decode(data.get(self.start..self.end).unwrap_or(&[])).into_owned()
    }
}

/// One name of a path, with the path of its receiver.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
struct Item {
    parent: Option<u32>,
    name: Text,
    head: Text,
    length: u32,
}

/// The paths of one file and the memo of the nodes that have one.
#[derive(Default)]
pub(crate) struct Paths {
    items: Vec<Item>,
    /// The path of each node that was asked for, by the id of the node. `None` is the empty path.
    memo: HashMap<usize, Option<u32>>,
}

pub(crate) use crate::source_input::is_script_root;

impl Paths {
    pub(crate) fn retained_texts(&mut self) -> impl Iterator<Item = &mut Text> {
        self.memo = HashMap::new();
        self.items
            .iter_mut()
            .flat_map(|item| [&mut item.name, &mut item.head])
    }

    fn push(&mut self, parent: Option<u32>, name: Text) -> u32 {
        let (head, length) = match parent.and_then(|at| self.items.get(at as usize)) {
            Some(item) => (item.head, item.length.saturating_add(1)),
            None => (name, 1),
        };
        self.items.push(Item {
            parent,
            name,
            head,
            length,
        });
        u32::try_from(self.items.len() - 1).unwrap_or(u32::MAX)
    }

    /// The first name of a path.
    pub(crate) fn head(&self, path: u32) -> Option<Text> {
        self.items.get(path as usize).map(|item| item.head)
    }

    /// The number of names of a path.
    pub(crate) fn length(&self, path: u32) -> u32 {
        self.items.get(path as usize).map_or(0, |item| item.length)
    }

    /// The names of a path, from the first to the last.
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    pub(crate) fn names(&self, path: u32, data: &[u8]) -> Vec<String> {
        let mut names = Vec::new();
        let mut next = Some(path);
        while let Some(item) = next.and_then(|at| self.items.get(at as usize)) {
            names.push(item.name.decode(data));
            next = item.parent;
        }
        names.reverse();
        names
    }

    /// `_static_path`: the names of `a`, `a.b` and `a.b.c`, and no path for any other node. A node
    /// that was asked for once is answered from the memo, so the members of one chain cost one pass.
    pub(crate) fn of(&mut self, cx: &Cx, node: Node) -> Option<u32> {
        // The members of the chain that wait for the path of their receiver, outermost first.
        let mut waiting: Vec<(usize, Text)> = Vec::new();
        let mut at = node;
        let base = loop {
            if let Some(known) = self.memo.get(&at.id()) {
                break *known;
            }
            let found = match cx.k(at) {
                K::Identifier
                | K::PropertyIdentifier
                | K::ShorthandPropertyIdentifier
                | K::ShorthandPropertyIdentifierPattern => {
                    let id = self.push(None, Text::of(at));
                    self.memo.insert(at.id(), Some(id));
                    break Some(id);
                }
                K::MemberExpression => member_parts(cx, at),
                _ => None,
            };
            let Some((object, name)) = found else {
                self.memo.insert(at.id(), None);
                break None;
            };
            waiting.push((at.id(), name));
            at = object;
        };
        let mut path = base;
        for (id, name) in waiting.into_iter().rev() {
            path = path.map(|parent| self.push(Some(parent), name));
            self.memo.insert(id, path);
        }
        path
    }
}

/// The receiver and the name of a member expression that has a plain name.
fn member_parts<'t>(cx: &Cx, node: Node<'t>) -> Option<(Node<'t>, Text)> {
    let object = cx.field(node, crate::kinds::F::Object)?;
    let property = cx.field(node, crate::kinds::F::Property)?;
    (cx.k(property) == K::PropertyIdentifier).then(|| (object, Text::of(property)))
}

#[cfg(test)]
#[path = "site_paths_tests.rs"]
mod tests;
