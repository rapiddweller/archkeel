// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: import extraction. The seven queries of `parse.py` are the reference: the single walk
// of `scan.rs` must find the same nodes in every file of the repository fixtures and in damaged
// copies of them.

use std::fs;
use std::path::{Path, PathBuf};

use tree_sitter::{Language, Node, Parser, Query, QueryCursor, StreamingIterator};
use tree_sitter_typescript::{LANGUAGE_TSX, LANGUAGE_TYPESCRIPT};

use super::*;
use crate::kinds::KindMap;
use crate::members::Cx;

const QUERIES: [(&str, &str); 7] = [
    (
        "references",
        "(import_statement) @import
         (export_statement source: (_)) @export
         (call_expression function: (import)) @dynamic
         (call_expression function: (identifier) @callee (#eq? @callee \"require\")) @require",
    ),
    ("comments", "(comment) @comment"),
    ("errors", "[(ERROR) (MISSING)] @error"),
    (
        "require_names",
        "([(identifier) (type_identifier) (shorthand_property_identifier)
           (shorthand_property_identifier_pattern)] @name (#eq? @name \"require\"))",
    ),
    (
        "require_members",
        "(member_expression property: (property_identifier) @name (#eq? @name \"require\")) @member
         (subscript_expression index: (string) @name (#match? @name \"^.require.$\")) @subscript
         (subscript_expression object: (identifier) @object (#eq? @object \"module\")) @subscript
         (pair_pattern key: (_) @key) @pair",
    ),
    (
        "module_names",
        "((identifier) @name (#eq? @name \"module\"))",
    ),
    (
        "create_require",
        "([(identifier) (property_identifier) (shorthand_property_identifier)
           (shorthand_property_identifier_pattern) (string_fragment)] @name
           (#eq? @name \"createRequire\"))",
    ),
];

type Ranges = Vec<(usize, usize)>;

fn ranges(nodes: &[Node]) -> Ranges {
    let mut found: Ranges = nodes
        .iter()
        .map(|n| (n.start_byte(), n.end_byte()))
        .collect();
    found.sort_unstable();
    found.dedup();
    found
}

/// The seven queries of `parse.py`, compiled for one grammar.
struct Reference {
    language: Language,
    queries: Vec<Query>,
}

impl Reference {
    fn new(language: Language) -> Self {
        let queries = QUERIES
            .iter()
            .map(|(_, text)| Query::new(&language, text).expect("a query"))
            .collect();
        Self { language, queries }
    }
}

/// The ranges that one query captures under one capture name.
fn queried(reference: &Reference, data: &[u8], root: Node, query: usize, wanted: &str) -> Ranges {
    let query = &reference.queries[query];
    let names = query.capture_names();
    let mut cursor = QueryCursor::new();
    let mut found: Ranges = Vec::new();
    let mut matches = cursor.captures(query, root, data);
    while let Some((matched, index)) = matches.next() {
        let capture = matched.captures[*index];
        if names[capture.index as usize] == wanted {
            found.push((capture.node.start_byte(), capture.node.end_byte()));
        }
    }
    found.sort_unstable();
    found.dedup();
    found
}

fn check(reference: &Reference, data: &[u8], label: &str) {
    let language = &reference.language;
    let mut parser = Parser::new();
    parser.set_language(language).expect("a language");
    let tree = parser.parse(data, None).expect("a tree");
    let root = tree.root_node();
    let source = Source::new(data);
    let map = KindMap::new(language);
    let mut walk = Walk::new(Cx {
        kinds: &map,
        source: &source,
    });
    let found = scan(&Kinds::new(language), &source, root, &mut walk);
    // The index of the query and the capture name, then what the walk found.
    let cases: [(usize, &str, Ranges); 11] = [
        (0, "import", ranges(&found.imports)),
        (0, "export", ranges(&found.exports)),
        (0, "dynamic", ranges(&found.dynamic)),
        (0, "require", ranges(&found.requires)),
        (1, "comment", ranges(&found.comments)),
        (2, "error", ranges(&found.errors)),
        (3, "name", ranges(&found.require_names)),
        (4, "member", ranges(&found.require_members)),
        (4, "subscript", ranges(&found.subscripts)),
        (4, "pair", ranges(&found.pairs)),
        (6, "name", ranges(&found.create_require)),
    ];
    for (query, capture, got) in cases {
        let want = queried(reference, data, root, query, capture);
        assert_eq!(got, want, "{label}: query {query} capture {capture}");
    }
    let modules = !queried(reference, data, root, 5, "name").is_empty();
    assert_eq!(found.module_name, modules, "{label}: module");
}

fn sources(directory: &Path, found: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(directory) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            if path
                .file_name()
                .is_some_and(|name| name != "node_modules" && name != "target")
            {
                sources(&path, found);
            }
        } else if path.extension().is_some_and(|ext| {
            ["ts", "tsx", "js", "jsx", "mts", "cts"]
                .iter()
                .any(|known| ext == *known)
        }) {
            found.push(path);
        }
    }
}

#[test]
fn the_single_walk_finds_what_the_seven_queries_find() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../");
    let mut files = Vec::new();
    sources(&root.join("fixtures"), &mut files);
    sources(&root.join("src/archkeel/studio/ui"), &mut files);
    assert!(files.len() > 50, "the fixtures are missing");
    let typescript = Reference::new(LANGUAGE_TYPESCRIPT.into());
    let tsx = Reference::new(LANGUAGE_TSX.into());
    for (index, path) in files.iter().enumerate() {
        let data = fs::read(path).expect("a source file");
        let text = String::from_utf8_lossy(&data).into_owned();
        let plain = path
            .extension()
            .is_some_and(|ext| ext == "ts" || ext == "mts" || ext == "cts");
        let reference = if plain { &typescript } else { &tsx };
        let name = path.display().to_string();
        check(reference, text.as_bytes(), &name);
        if index % 4 == 0 {
            // Damaged copies: cut inside the file, and a stray token in the middle.
            let cut = (index * 7919) % (text.len() + 1);
            let at = text
                .char_indices()
                .map(|(at, _)| at)
                .find(|at| *at >= cut)
                .unwrap_or(0);
            check(reference, &text.as_bytes()[..at], &format!("{name} cut"));
            let half = text
                .char_indices()
                .map(|(at, _)| at)
                .find(|at| *at >= text.len() / 2)
                .unwrap_or(0);
            let stray = format!("{}\n}} ((( require(`${{ module[x] \n", &text[..half]);
            check(reference, stray.as_bytes(), &format!("{name} stray"));
        }
    }
}
