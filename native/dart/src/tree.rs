// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The tree helpers of the Dart parse, as `_Source`, `_walk`, `_named` and their neighbours in
//! `analyzer/dart/parse.py`. The walk uses no recursion, so a deep tree cannot overflow the
//! stack (AD-369).

use tree_sitter::{Node, TreeCursor};

use crate::pytext::first_chars;
use crate::syntax::Span;

/// The excerpt of a span holds at most 400 characters. A character uses at most 4 bytes; 4 more
/// bytes let the decoder see the whole last character.
const EXCERPT_CHARS: usize = 400;
const EXCERPT_BYTES: usize = EXCERPT_CHARS * 4 + 4;

/// The bytes of one source and the start of each line, as `_Source` holds them.
pub(crate) struct Source<'a> {
    pub(crate) data: &'a [u8],
    starts: Vec<usize>,
}

impl<'a> Source<'a> {
    /// The line starts: 0 and the end of each `\r\n`, `\n`, `\r`, U+2028 and U+2029.
    pub(crate) fn new(data: &'a [u8]) -> Self {
        let mut starts = vec![0];
        let mut index = 0usize;
        while let Some(&value) = data.get(index) {
            let width = match value {
                b'\r' if data.get(index.saturating_add(1)) == Some(&b'\n') => 2,
                b'\n' | b'\r' => 1,
                0xe2 if data.get(index.saturating_add(1)) == Some(&0x80)
                    && matches!(data.get(index.saturating_add(2)), Some(0xa8 | 0xa9)) =>
                {
                    3
                }
                _ => 0,
            };
            index = index.saturating_add(width.max(1));
            if width > 0 {
                starts.push(index);
            }
        }
        Self { data, starts }
    }

    /// `bytes[start:end].decode("utf-8", "replace")`.
    pub(crate) fn decode(&self, start: usize, end: usize) -> String {
        let end = end.min(self.data.len());
        self.data
            .get(start.min(end)..end)
            .map(|bytes| String::from_utf8_lossy(bytes).into_owned())
            .unwrap_or_default()
    }

    /// `_Source.text`.
    pub(crate) fn text(&self, node: Node<'_>) -> String {
        self.decode(node.start_byte(), node.end_byte())
    }

    /// `_Source.span`.
    pub(crate) fn span(&self, node: Node<'_>) -> Span {
        self.span_bytes(node.start_byte(), node.end_byte())
    }

    /// `_span_bytes`: the lines, the UTF-16 column and the excerpt of a byte range.
    pub(crate) fn span_bytes(&self, start: usize, end: usize) -> Span {
        let line = self.line(start);
        let line_start = self
            .starts
            .get(line.saturating_sub(1))
            .copied()
            .unwrap_or(0);
        let prefix = self.decode(line_start, start);
        let head = self.decode(start, end.min(start.saturating_add(EXCERPT_BYTES)));
        Span {
            line,
            end_line: self.line(end),
            column: prefix.chars().map(char::len_utf16).sum(),
            excerpt: first_chars(&head, EXCERPT_CHARS).to_owned(),
            start_byte: start,
            end_byte: end,
        }
    }

    /// `bisect_right(starts, offset)`: the line of a byte, from 1.
    fn line(&self, offset: usize) -> usize {
        self.starts.partition_point(|start| *start <= offset)
    }
}

/// `_walk`: the node and each node below it, in document order, without recursion.
pub(crate) struct Walk<'t> {
    cursor: TreeCursor<'t>,
    /// The depth of the cursor below the first node.
    pub(crate) depth: usize,
    started: bool,
}

impl<'t> Walk<'t> {
    pub(crate) fn new(node: Node<'t>) -> Self {
        Self {
            cursor: node.walk(),
            depth: 0,
            started: false,
        }
    }
}

impl<'t> Iterator for Walk<'t> {
    type Item = Node<'t>;

    fn next(&mut self) -> Option<Node<'t>> {
        if !self.started {
            self.started = true;
            return Some(self.cursor.node());
        }
        if self.cursor.goto_first_child() {
            self.depth = self.depth.saturating_add(1);
            return Some(self.cursor.node());
        }
        while self.depth > 0 {
            if self.cursor.goto_next_sibling() {
                return Some(self.cursor.node());
            }
            self.cursor.goto_parent();
            self.depth = self.depth.saturating_sub(1);
        }
        None
    }
}

pub(crate) fn walk(node: Node<'_>) -> Walk<'_> {
    Walk::new(node)
}

/// `node.children`: each child, also the anonymous tokens and the comments.
pub(crate) fn children(node: Node<'_>) -> Vec<Node<'_>> {
    node.children(&mut node.walk()).collect()
}

/// `node.named_children`.
pub(crate) fn named_children(node: Node<'_>) -> Vec<Node<'_>> {
    node.named_children(&mut node.walk()).collect()
}

/// `_named`: the child of the field `kind`, else the first named child of that kind.
pub(crate) fn named<'t>(node: Node<'t>, kind: &str) -> Option<Node<'t>> {
    node.child_by_field_name(kind)
        .or_else(|| first_named_of(node, &[kind]))
}

/// `_named` on an optional node.
pub(crate) fn named_in<'t>(node: Option<Node<'t>>, kind: &str) -> Option<Node<'t>> {
    node.and_then(|node| named(node, kind))
}

/// `_named_all`: the named children of one kind.
pub(crate) fn named_all<'t>(node: Option<Node<'t>>, kind: &str) -> Vec<Node<'t>> {
    node.map(|node| {
        named_children(node)
            .into_iter()
            .filter(|child| child.kind() == kind)
            .collect()
    })
    .unwrap_or_default()
}

/// The first named child of one of `kinds`.
pub(crate) fn first_named_of<'t>(node: Node<'t>, kinds: &[&str]) -> Option<Node<'t>> {
    named_children(node)
        .into_iter()
        .find(|child| kinds.contains(&child.kind()))
}

/// The first node of one of `kinds` in the walk of `node`.
pub(crate) fn first_in_walk<'t>(node: Node<'t>, kinds: &[&str]) -> Option<Node<'t>> {
    walk(node).find(|item| kinds.contains(&item.kind()))
}

/// `_first_identifier`.
pub(crate) fn first_identifier(node: Option<Node<'_>>, source: &Source<'_>) -> Option<String> {
    let found = first_in_walk(node?, &["identifier", "type_identifier"])?;
    Some(source.text(found))
}

/// `_text_children`: the identifiers below a node, joined with dots.
pub(crate) fn text_children(node: Node<'_>, source: &Source<'_>) -> String {
    walk(node)
        .filter(|item| item.kind() == "identifier")
        .map(|item| source.text(item))
        .collect::<Vec<_>>()
        .join(".")
}

/// The position of `node` among the named children of its parent, with those children.
pub(crate) fn position<'t>(node: Node<'t>) -> Option<(Vec<Node<'t>>, Option<usize>)> {
    let siblings = named_children(node.parent()?);
    let at = siblings.iter().position(|item| *item == node);
    Some((siblings, at))
}

/// `_prefix`: the text between the previous named sibling (or the parent start) and the node.
pub(crate) fn prefix(node: Node<'_>, source: &Source<'_>) -> String {
    let Some(parent) = node.parent() else {
        return String::new();
    };
    let start = match position(node) {
        Some((siblings, Some(at))) if at > 0 => siblings
            .get(at.saturating_sub(1))
            .map_or(parent.start_byte(), Node::end_byte),
        _ => parent.start_byte(),
    };
    source.decode(start, node.start_byte())
}
