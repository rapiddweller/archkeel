// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::parse::parse;

fn module(rel: &str, text: &str) -> Module {
    let tree = parse(text, 13).expect("valid source");
    Module::new(rel.to_owned(), "app.x.y".to_owned(), text.to_owned(), tree)
}

#[test]
fn a_statement_has_the_cpython_location_and_excerpt() {
    let found = module(
        "app/x/y.py",
        "x = 'é'; import os  \t\nfrom a import (b,\n    c)\n",
    );
    let mut evidence = EvidenceMap::new();
    let ids: Vec<String> = found
        .tree
        .body
        .iter()
        .map(|statement| found.evidence(&mut evidence, statement))
        .collect();
    let rows: Vec<(i64, i64, i64, &str)> = ids
        .iter()
        .map(|id| {
            let item = &evidence[id];
            (item.line, item.end_line, item.column, item.excerpt.as_str())
        })
        .collect();
    let first = "x = 'é'; import os";
    assert_eq!(
        rows,
        [
            (1, 1, 0, first),
            (1, 1, 10, first),
            (2, 3, 0, "from a import (b,")
        ]
    );
    assert_eq!(found.package, "app.x");
    assert!(!found.is_init());
}

#[test]
fn the_file_evidence_cites_line_one_or_the_file() {
    let mut evidence = EvidenceMap::new();
    let id = module("app/__init__.py", "   \nx = 1\n").file_evidence(&mut evidence);
    assert_eq!(
        (evidence[&id].line, evidence[&id].excerpt.as_str()),
        (0, "")
    );
    let id = module("app/__init__.py", "# head \x1c\nx = 1\n").file_evidence(&mut evidence);
    assert_eq!(
        (evidence[&id].line, evidence[&id].excerpt.as_str()),
        (1, "# head")
    );
    assert!(module("app/__init__.py", "").is_init());
}
