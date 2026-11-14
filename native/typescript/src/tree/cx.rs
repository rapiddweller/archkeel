// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The grammar and the text of one file: the context that every reader of a node needs.

use tree_sitter::Node;

use crate::kinds::{KindMap, F, K};
use crate::source::{Source, Span};
use crate::tree::nodes::each_child;

/// The grammar and the text of one file: what every reader of a node needs.
#[derive(Clone, Copy)]
pub(crate) struct Cx<'a> {
    pub kinds: &'a KindMap,
    pub source: &'a Source<'a>,
}

impl Cx<'_> {
    pub(crate) fn k(&self, node: Node) -> K {
        self.kinds.of(node)
    }

    pub(crate) fn text(&self, node: Node) -> String {
        self.source.text(node)
    }

    pub(crate) fn span(&self, node: Node) -> Span {
        self.source.span(node, None)
    }

    pub(crate) fn bytes(&self, node: Node) -> &[u8] {
        self.source
            .data
            .get(node.start_byte()..node.end_byte())
            .unwrap_or(&[])
    }

    pub(crate) fn field<'t>(&self, node: Node<'t>, field: F) -> Option<Node<'t>> {
        self.kinds.field(node, field)
    }

    /// The expression inside parentheses, `as`, `satisfies`, `!` and `<T>`: the value is the same
    /// at run time. Each reader of a write target uses this one helper.
    pub(crate) fn unwrapped<'t>(&self, node: Node<'t>) -> Node<'t> {
        let mut node = node;
        loop {
            let inner = match node.kind() {
                "parenthesized_expression"
                | "as_expression"
                | "satisfies_expression"
                | "non_null_expression" => node.named_child(0),
                "type_assertion" => node.named_child(node.named_child_count().saturating_sub(1)),
                _ => None,
            };
            match inner {
                Some(inner) => node = inner,
                None => return node,
            }
        }
    }

    /// Whether a child of `node` has the kind `kind`.
    pub(crate) fn has_child(&self, node: Node, kind: K) -> bool {
        let mut found = false;
        each_child(node, |child| found |= self.k(child) == kind);
        found
    }
}
