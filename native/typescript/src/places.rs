// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Where the tree has an import-bearing node, found by the query of `parse.py` and not by the walk
//! of `scan.rs`. The extraction invariant (`imports.rs`, `check_extracted`) compares the outcome of
//! the extraction with this count; a count that the walk itself fed would compare the output with
//! itself, so a node that the walk loses would go unseen.

use std::collections::HashSet;

use tree_sitter::{Language, Node, Query, QueryCursor, StreamingIterator};

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
        let Some(query) = &self.0 else {
            return 0;
        };
        let names = query.capture_names();
        let mut cursor = QueryCursor::new();
        let mut nodes = HashSet::new();
        let mut matches = cursor.captures(query, root, source.data);
        while let Some((matched, index)) = matches.next() {
            let capture = matched.captures.get(*index);
            if let Some(capture) = capture.filter(|c| names.get(c.index as usize) == Some(&"place"))
            {
                nodes.insert(capture.node.id());
            }
        }
        nodes.len()
    }
}
