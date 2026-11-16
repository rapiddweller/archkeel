// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Where the tree has an import-bearing node, found independently of the walk
//! of `scan.rs`. The extraction invariant (`imports.rs`, `check_extracted`) compares the outcome of
//! the extraction with this count; a count that the walk itself fed would compare the output with
//! itself, so a node that the walk loses would go unseen.

use tree_sitter::{Language, Node, Query, TreeCursor};

use crate::source::Source;

const QUERY: &str = "(import_statement) @place
    (export_statement source: (_)) @place
    (call_expression function: (import)) @place
    (call_expression function: (identifier) @callee (#eq? @callee \"require\")) @place";

/// The query of the references of `parse.py`, compiled for one grammar.
pub(crate) struct PlaceQuery(Option<Query>);

impl PlaceQuery {
    pub(crate) fn new(language: &Language) -> Self {
        Self(Query::new(language, QUERY).ok())
    }

    /// How many import-bearing nodes the tree has under `root`. A node counts once, and a grammar
    /// without the query counts none. The count is of nodes and not of positions: a reference
    /// that names a type query starts at the `typeof`, not at the call.
    pub(crate) fn count(&self, source: &Source, root: Node) -> usize {
        if self.0.is_none() {
            return 0;
        }
        let mut cursor = root.walk();
        let mut count = 0;
        loop {
            let node = cursor.node();
            let place = match node.kind() {
                "import_statement" => true,
                "export_statement" => node
                    .child_by_field_name("source")
                    .is_some_and(|source| source.is_named()),
                "call_expression" => node
                    .child_by_field_name("function")
                    .is_some_and(|function| {
                        function.kind() == "import"
                            || (function.kind() == "identifier"
                                && source.data.get(function.byte_range()) == Some(b"require"))
                    }),
                _ => false,
            };
            count += usize::from(place);
            if !next(&mut cursor) {
                return count;
            }
        }
    }
}

fn next(cursor: &mut TreeCursor) -> bool {
    if cursor.goto_first_child() {
        return true;
    }
    loop {
        if cursor.goto_next_sibling() {
            return true;
        }
        if !cursor.goto_parent() {
            return false;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;
    use tree_sitter::{Parser, QueryCursor, StreamingIterator};

    fn query_count(query: &Query, root: Node, text: &str) -> usize {
        let mut cursor = QueryCursor::new();
        let mut captures = cursor.captures(query, root, text.as_bytes());
        let mut nodes = HashSet::new();
        while let Some((matched, index)) = captures.next() {
            let capture = matched.captures[*index];
            if query.capture_names()[capture.index as usize] == "place" {
                nodes.insert(capture.node.id());
            }
        }
        nodes.len()
    }

    #[test]
    fn independent_walk_matches_query_on_both_grammars() {
        let examples = [
            "import x from 'x'; export {x} from 'y'; export {x}; import('z'); require('a');",
            "a.b().b(); obj.require('a'); require.resolve('b'); (require)('c'); require(require('d'));",
            "import { ; export * from ; require( ; import( ; const x = <div/>;",
            "function require() {} require('x'); requirex('x'); new require('x');",
        ];
        for language in [
            tree_sitter_typescript::LANGUAGE_TYPESCRIPT,
            tree_sitter_typescript::LANGUAGE_TSX,
        ] {
            let language: Language = language.into();
            let query = Query::new(&language, QUERY).unwrap();
            let mut parser = Parser::new();
            parser.set_language(&language).unwrap();
            for text in examples {
                let tree = parser.parse(text, None).unwrap();
                let root = tree.root_node();
                assert_eq!(
                    PlaceQuery::new(&language).count(&Source::new(text.as_bytes()), root),
                    query_count(&query, root, text),
                    "{text}"
                );
            }
        }
    }

    #[test]
    fn long_call_chain_place_count_finishes_quickly() {
        let language: Language = tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into();
        let mut parser = Parser::new();
        parser.set_language(&language).unwrap();
        let text = format!("a{};", ".b()".repeat(40_000));
        let tree = parser.parse(&text, None).unwrap();
        let source = Source::new(text.as_bytes());
        let places = PlaceQuery::new(&language);
        let started = std::time::Instant::now();
        assert_eq!(places.count(&source, tree.root_node()), 0);
        assert!(
            started.elapsed().as_secs_f64() < 3.0,
            "place count took {:?}",
            started.elapsed()
        );
    }
}
