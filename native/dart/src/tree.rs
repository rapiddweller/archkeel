// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The tree helpers of the Dart parse, as `_Source`, `_walk`, `_named` and their neighbours in
//! `analyzer/dart/parse.py`. The walk uses no recursion, so a deep tree cannot overflow the
//! stack (AD-369).

use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::rc::Rc;

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
    /// The source is valid UTF-8: then a column can continue from an earlier one on its line.
    text: bool,
    /// The last column: its line start, its byte and its UTF-16 column.
    last: Cell<(usize, usize, usize)>,
    /// The bytes decoded for columns so far: the site walk counts them as work.
    decoded: Cell<usize>,
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
        Self {
            data,
            starts,
            text: std::str::from_utf8(data).is_ok(),
            last: Cell::new((0, 0, 0)),
            decoded: Cell::new(0),
        }
    }

    /// The bytes decoded for columns since the last call.
    pub(crate) fn take_decoded(&self) -> usize {
        self.decoded.replace(0)
    }

    /// `len(prefix.encode("utf-16-le")) // 2` for the prefix of the line before `start`. In
    /// valid UTF-8 the column continues from the last column of the same line when `start` is
    /// not before it, so a long line with many sites is read once (AD-376).
    fn column(&self, line_start: usize, start: usize) -> usize {
        let (last_line, last_byte, last_column) = self.last.get();
        // Two decodes equal one only when they split the text at a character boundary.
        let boundary = self
            .data
            .get(last_byte)
            .is_none_or(|byte| (byte & 0xc0) != 0x80);
        let from_last = self.text && boundary && last_line == line_start && last_byte <= start;
        let (from, base) = if from_last {
            (last_byte, last_column)
        } else {
            (line_start, 0)
        };
        let part = self.decode(from, start);
        self.decoded.set(
            self.decoded
                .get()
                .saturating_add(start.saturating_sub(from)),
        );
        let column = base.saturating_add(part.chars().map(char::len_utf16).sum::<usize>());
        self.last.set((line_start, start, column));
        column
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
        let column = self.column(line_start, start);
        let head = self.decode(start, end.min(start.saturating_add(EXCERPT_BYTES)));
        Span {
            line,
            end_line: self.line(end),
            column,
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

/// `_prefix`: the text between the previous named sibling (or the parent start) and the node.
/// `parent` is the parent of `node`; the caller has it, and `Node::parent` walks down from the
/// root, which costs the position of the node in a long list.
pub(crate) fn prefix<'t>(
    node: Node<'t>,
    parent: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> String {
    let family = work.family(parent);
    let start = match family.position(node) {
        Some(at) if at > 0 => family
            .nodes
            .get(at.saturating_sub(1))
            .map_or(parent.start_byte(), Node::end_byte),
        _ => parent.start_byte(),
    };
    source.decode(start, node.start_byte())
}

/// `_walk` with the ancestors of each node, root first, without recursion. The ancestors replace
/// `_ancestors`, which Tree-sitter can only give with a walk down from the root for each parent.
/// `visit` returns false to stop the walk.
pub(crate) fn walk_with_path<'t>(
    root: Node<'t>,
    mut visit: impl FnMut(Node<'t>, &[Node<'t>]) -> bool,
) {
    let mut cursor = root.walk();
    let mut path: Vec<Node<'t>> = Vec::new();
    loop {
        let node = cursor.node();
        if !visit(node, &path) {
            return;
        }
        if cursor.goto_first_child() {
            path.push(node);
            continue;
        }
        loop {
            if path.is_empty() {
                return;
            }
            if cursor.goto_next_sibling() {
                break;
            }
            if !cursor.goto_parent() {
                return;
            }
            path.pop();
        }
    }
}

/// The named children of one parent and the position of each, read once for each parent.
pub(crate) struct Family<'t> {
    pub(crate) nodes: Vec<Node<'t>>,
    index: HashMap<usize, usize>,
    /// `later[i]`: the selectors of `nodes[i..]`. A rule that asks it for each node reads one
    /// value, where Python scans the rest of the list again.
    later: Vec<Later>,
}

/// The selectors in a run of siblings: one with a member access (`_is_member_receiver`), one
/// with arguments (`_is_call_callee`, `_is_call_selector`) and one with an index
/// (`_selector_has_index`).
#[derive(Clone, Copy, Default)]
pub(crate) struct Later {
    pub(crate) member: bool,
    pub(crate) call: bool,
    pub(crate) index: bool,
}

impl Later {
    /// The facts of one sibling, and the number of children that it reads.
    fn of(node: Node<'_>) -> (Self, usize) {
        if node.kind() != "selector" {
            return (Self::default(), 0);
        }
        let children = named_children(node);
        let assignable = children
            .iter()
            .find(|child| child.kind() == "unconditional_assignable_selector");
        let found = Self {
            member: assignable.is_some(),
            call: named(node, "argument_part").is_some(),
            index: assignable.is_some_and(|item| named(*item, "index_selector").is_some()),
        };
        (found, children.len())
    }

    fn or(self, other: Self) -> Self {
        Self {
            member: self.member || other.member,
            call: self.call || other.call,
            index: self.index || other.index,
        }
    }
}

impl<'t> Family<'t> {
    /// The position of `node` among the named children: `next(i for i, item in ... if item ==
    /// node)` of Python.
    pub(crate) fn position(&self, node: Node<'t>) -> Option<usize> {
        self.index.get(&node.id()).copied()
    }

    /// The named children after `node`, or `None` when `node` is not one of them.
    pub(crate) fn after(&self, node: Node<'t>) -> Option<&[Node<'t>]> {
        let at = self.position(node)?;
        Some(self.nodes.get(at.saturating_add(1)..).unwrap_or_default())
    }

    /// The selectors of the named children from position `from` on.
    pub(crate) fn later(&self, from: usize) -> Later {
        self.later.get(from).copied().unwrap_or_default()
    }
}

/// The work of the site walks, counted in visited nodes and scanned siblings. Python has no
/// limit and takes hours on some hostile sources; native stops at the limit and names the file
/// with a concern (AD-376). It also holds the named children of each parent that a site rule
/// reads: Python reads them again for each node, which grows with the square of a long list.
pub(crate) struct Work<'t> {
    spent: Cell<u64>,
    limit: u64,
    families: RefCell<HashMap<usize, Rc<Family<'t>>>>,
}

impl<'t> Work<'t> {
    pub(crate) fn new(limit: u64) -> Self {
        Self {
            spent: Cell::new(0),
            limit,
            families: RefCell::new(HashMap::new()),
        }
    }

    pub(crate) fn charge(&self, units: usize) {
        let units = u64::try_from(units).unwrap_or(u64::MAX);
        self.spent.set(self.spent.get().saturating_add(units));
    }

    pub(crate) fn exceeded(&self) -> bool {
        self.spent.get() > self.limit
    }

    /// The gap when the work passes the limit: a walk that charges its work asks it for each
    /// node, so no walk runs on after the limit.
    pub(crate) fn within(&self, gap: Gap) -> Result<(), Gap> {
        if self.exceeded() {
            Err(gap)
        } else {
            Ok(())
        }
    }

    #[cfg(test)]
    pub(crate) fn spent(&self) -> u64 {
        self.spent.get()
    }

    /// The share of the limit spent so far, in thousandths, for the dump.
    pub(crate) fn permille(&self) -> u64 {
        self.spent
            .get()
            .saturating_mul(1000)
            .checked_div(self.limit)
            .unwrap_or(u64::MAX)
    }

    /// The named children of `parent`, read once.
    pub(crate) fn family(&self, parent: Node<'t>) -> Rc<Family<'t>> {
        if let Some(found) = self.families.borrow().get(&parent.id()) {
            return Rc::clone(found);
        }
        let nodes = named_children(parent);
        self.charge(nodes.len());
        let index = nodes
            .iter()
            .enumerate()
            .map(|(at, node)| (node.id(), at))
            .collect();
        let mut later = vec![Later::default(); nodes.len().saturating_add(1)];
        for (at, node) in nodes.iter().enumerate().rev() {
            let (found, read) = Later::of(*node);
            self.charge(read);
            let next = later.get(at.saturating_add(1)).copied().unwrap_or_default();
            if let Some(slot) = later.get_mut(at) {
                *slot = found.or(next);
            }
        }
        let family = Rc::new(Family {
            nodes,
            index,
            later,
        });
        self.families
            .borrow_mut()
            .insert(parent.id(), Rc::clone(&family));
        family
    }
}

/// A state that the site walks cannot reach on a Tree-sitter tree. The file gets a concern, so
/// a wrong assumption gives a gap and never a wrong site.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct Gap(pub(crate) &'static str);
