// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Source positions of one file, as `parse.py` reads them.
//!
//! The text with its line starts, and the 1-based line and UTF-16 column of a node.

use std::cell::RefCell;
use std::collections::HashMap;

use tree_sitter::Node;

use crate::pytext::{decode, first_chars, utf16_len};

/// A 1-based line and UTF-16 column, as the TypeScript compiler reports them.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub(crate) struct Span {
    pub line: i64,
    pub end_line: i64,
    pub column: i64,
    pub excerpt: String,
}

/// The file and start position of an import statement.
pub(crate) struct FileSite {
    pub(crate) rel: String,
    pub(crate) line: i64,
    pub(crate) column: i64,
}

impl FileSite {
    pub(crate) fn key(&self) -> FileSiteKey<'_> {
        FileSiteKey {
            rel: &self.rel,
            line: self.line,
            column: self.column,
        }
    }
}

/// A borrowed file position for matching an import statement to a loader call.
#[derive(PartialEq, Eq, Hash)]
pub(crate) struct FileSiteKey<'a> {
    pub(crate) rel: &'a str,
    pub(crate) line: i64,
    pub(crate) column: i64,
}

/// The text of one file with its line starts.
pub(crate) struct Source<'a> {
    pub data: &'a [u8],
    starts: Vec<usize>,
    /// The columns of the long lines, by line (see `column`).
    long_lines: RefCell<HashMap<usize, Option<Vec<u32>>>>,
}

impl<'a> Source<'a> {
    /// The line starts of `_LINE_BREAK`: `\r\n`, `\n`, `\r`, U+2028 and U+2029.
    pub(crate) fn new(data: &'a [u8]) -> Self {
        let mut starts = vec![0];
        let mut index = 0;
        while index < data.len() {
            index += match (data[index], data.get(index + 1), data.get(index + 2)) {
                (b'\r', Some(b'\n'), _) => 2,
                (b'\r' | b'\n', _, _) => 1,
                (0xe2, Some(0x80), Some(0xa8 | 0xa9)) => 3,
                _ => {
                    index += 1;
                    continue;
                }
            };
            starts.push(index);
        }
        Self {
            data,
            starts,
            long_lines: RefCell::new(HashMap::new()),
        }
    }

    pub(crate) fn text(&self, node: Node) -> String {
        decode(&self.data[node.start_byte()..node.end_byte()]).into_owned()
    }

    fn line_of(&self, byte: usize) -> usize {
        self.starts.partition_point(|start| *start <= byte)
    }

    /// The UTF-16 column (1-based) of the byte `byte` on `line`, as `len(prefix.encode("utf-16-le")) // 2 + 1`
    /// of the decoded line prefix. A long line is measured once: an ASCII line has one unit for each
    /// byte, and another long line gets a table of the units before each byte.
    fn column(&self, line: usize, byte: usize) -> i64 {
        let begin = self.starts[line - 1];
        let width = byte - begin;
        if width <= SHORT_PREFIX {
            return utf16_len(&decode(&self.data[begin..byte])) as i64 + 1;
        }
        let mut lines = self.long_lines.borrow_mut();
        let table = lines.entry(line).or_insert_with(|| {
            let end = self.starts.get(line).copied().unwrap_or(self.data.len());
            units_before(&self.data[begin..end])
        });
        match table {
            None => width as i64 + 1,
            Some(units) => units.get(width).map_or(width, |units| *units as usize) as i64 + 1,
        }
    }

    /// `_text(node)[:400]`. A text of 400 ASCII bytes needs no decoding. Another text is cut after
    /// 1 600 bytes first, because 400 characters are at most 1 600 bytes, so a long node is never
    /// decoded in full.
    fn excerpt(&self, node: Node) -> String {
        let (start, end) = (node.start_byte(), node.end_byte());
        let short = &self.data[start..end.min(start + 400)];
        if short.is_ascii() {
            return decode(short).into_owned();
        }
        let head = decode(&self.data[start..end.min(start + EXCERPT_BYTES)]);
        first_chars(&head, 400).to_owned()
    }

    /// `_Source.span`: the position of `node`, with the excerpt and column of `start` if given.
    pub(crate) fn span(&self, node: Node, start: Option<Node>) -> Span {
        let first = start.unwrap_or(node);
        let line = self.line_of(first.start_byte());
        Span {
            line: line as i64,
            end_line: self.line_of(node.end_byte()) as i64,
            column: self.column(line, first.start_byte()),
            excerpt: self.excerpt(first),
        }
    }
}

/// A line prefix up to this length is decoded for each node; a longer one uses the cache.
const SHORT_PREFIX: usize = 256;
/// The bytes that hold 400 characters: UTF-8 has at most four bytes in a character.
const EXCERPT_BYTES: usize = 1600;

/// For a line with a non-ASCII byte: the UTF-16 units of `decode(line[..i])` for each `i`; `None`
/// for an ASCII line. A cut inside a character or inside bytes that are not UTF-8 decodes to one
/// replacement character, as `str(bytes, "utf-8", "replace")` does.
fn units_before(line: &[u8]) -> Option<Vec<u32>> {
    if line.is_ascii() {
        return None;
    }
    let mut table = Vec::with_capacity(line.len() + 1);
    let mut units = 0u32;
    table.push(0);
    for chunk in line.utf8_chunks() {
        for character in chunk.valid().chars() {
            table.extend(std::iter::repeat_n(units + 1, character.len_utf8() - 1));
            units += character.len_utf16() as u32;
            table.push(units);
        }
        let bad = chunk.invalid().len();
        if bad > 0 {
            table.extend(std::iter::repeat_n(units + 1, bad - 1));
            units += 1;
            table.push(units);
        }
    }
    Some(table)
}
