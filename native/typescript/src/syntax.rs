// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Source positions and the grammar of one file, as `parse.py` reads them.
//!
//! This is the only module that touches the parser. The parser runs inside the collector
//! process, which the host bounds, because it reads untrusted source.

use tree_sitter::{Language, Node, Parser, Query};
use tree_sitter_typescript::{LANGUAGE_TSX, LANGUAGE_TYPESCRIPT};

use crate::pytext::{decode, first_chars, utf16_len};

/// A 1-based line and UTF-16 column, as the TypeScript compiler reports them.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Span {
    pub line: i64,
    pub end_line: i64,
    pub column: i64,
    pub excerpt: String,
}

/// The text of one file with its line starts.
pub struct Source<'a> {
    pub data: &'a [u8],
    starts: Vec<usize>,
}

impl<'a> Source<'a> {
    /// The line starts of `_LINE_BREAK`: `\r\n`, `\n`, `\r`, U+2028 and U+2029.
    pub fn new(data: &'a [u8]) -> Self {
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
        Self { data, starts }
    }

    pub fn text(&self, node: Node) -> String {
        decode(&self.data[node.start_byte()..node.end_byte()]).into_owned()
    }

    fn line_of(&self, byte: usize) -> usize {
        self.starts.partition_point(|start| *start <= byte)
    }

    /// `_Source.span`: the position of `node`, with the excerpt and column of `start` if given.
    pub fn span(&self, node: Node, start: Option<Node>) -> Span {
        let first = start.unwrap_or(node);
        let line = self.line_of(first.start_byte());
        let prefix = decode(&self.data[self.starts[line - 1]..first.start_byte()]);
        let text = self.text(first);
        Span {
            line: line as i64,
            end_line: self.line_of(node.end_byte()) as i64,
            column: utf16_len(&prefix) as i64 + 1,
            excerpt: first_chars(&text, 400).to_owned(),
        }
    }
}

/// One grammar with the queries of this collector.
pub struct Grammar {
    pub language: Language,
    pub references: Query,
    pub comments: Query,
    pub errors: Query,
    pub require_names: Query,
    pub require_members: Query,
    pub module_names: Query,
    pub create_require: Query,
}

impl Grammar {
    fn new(language: Language) -> Self {
        let query =
            |text: &str| Query::new(&language, text).expect("the query matches the grammar");
        Self {
            references: query(
                "(import_statement) @import
                 (export_statement source: (_)) @export
                 (call_expression function: (import)) @dynamic
                 (call_expression function: (identifier) @callee (#eq? @callee \"require\")) @require",
            ),
            comments: query("(comment) @comment"),
            errors: query("[(ERROR) (MISSING)] @error"),
            require_names: query(
                "([(identifier) (type_identifier) (shorthand_property_identifier)
                   (shorthand_property_identifier_pattern)] @name (#eq? @name \"require\"))",
            ),
            require_members: query(
                "(member_expression property: (property_identifier) @name (#eq? @name \"require\")) @member
                 (subscript_expression index: (string) @name (#match? @name \"^.require.$\")) @subscript
                 (subscript_expression object: (identifier) @object (#eq? @object \"module\")) @subscript
                 (pair_pattern key: (_) @key) @pair",
            ),
            module_names: query("((identifier) @name (#eq? @name \"module\"))"),
            create_require: query(
                "([(identifier) (property_identifier) (shorthand_property_identifier)
                   (shorthand_property_identifier_pattern) (string_fragment)] @name
                   (#eq? @name \"createRequire\"))",
            ),
            language,
        }
    }
}

/// The parser, the two grammars and their queries, built once for a collection.
pub struct Parsers {
    parser: Parser,
    typescript: Grammar,
    tsx: Grammar,
}

impl Parsers {
    pub fn new() -> Self {
        Self {
            parser: Parser::new(),
            typescript: Grammar::new(LANGUAGE_TYPESCRIPT.into()),
            tsx: Grammar::new(LANGUAGE_TSX.into()),
        }
    }

    /// Parse with the grammar without JSX when `typescript` is set, else with the TSX grammar.
    pub fn parse(
        &mut self,
        typescript: bool,
        data: &[u8],
    ) -> Option<(tree_sitter::Tree, &Grammar)> {
        let grammar = if typescript {
            &self.typescript
        } else {
            &self.tsx
        };
        self.parser.set_language(&grammar.language).ok()?;
        Some((self.parser.parse(data, None)?, grammar))
    }
}
