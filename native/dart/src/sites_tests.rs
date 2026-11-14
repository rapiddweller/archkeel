// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The expected values come from the Python collector of release 4.0.1 (Python 3.11).
// The test that compared whole files is deleted with the Python core.

use super::*;
use crate::parse::DartParser;
use crate::syntax::{SiteKind, SiteUse, Syntax};

const PINNED_WORK: u64 = 825;

fn parse(text: &str) -> Syntax {
    DartParser::new().unwrap().parse(text.as_bytes())
}

fn sites_of(text: &str, limit: u64) -> Result<Vec<Site>, Gap> {
    let mut parser = tree_sitter::Parser::new();
    parser
        .set_language(&archkeel_dart_grammar::LANGUAGE.into())
        .unwrap();
    let tree = parser.parse(text, None).unwrap();
    let source = Source::new(text.as_bytes());
    sites(tree.root_node(), &source, &[], &[], &Work::new(limit))
}

#[test]
fn the_work_limit_stops_the_site_walks_with_a_gap() {
    let text = "void f() { g(h(1)); }\n";
    assert!(sites_of(text, 1 << 20).is_ok());
    let stopped = sites_of(text, 3);
    assert_eq!(
        stopped.err(),
        Some(Gap("the work passes the limit of the site walks"))
    );
}

#[test]
fn the_work_limit_grows_with_the_size() {
    assert_eq!(work_limit(0), WORK_BASE);
    assert_eq!(work_limit(10), WORK_BASE + 10 * WORK_PER_BYTE);
    assert_eq!(work_limit(usize::MAX), u64::MAX);
}

#[test]
fn a_tree_at_the_depth_limit_gives_no_sites() {
    let text = format!("var x = {}1{};\n", "(".repeat(2000), ")".repeat(2000));
    let syntax = parse(&text);
    assert!(syntax.sites.is_empty());
    assert!(syntax.first_error.is_some());
}

#[test]
fn the_sites_sort_by_start_and_then_by_kind() {
    // A parameter starts a binding and a type or a reference at the same byte; Python sorts by
    // the value of the kind after the start.
    let syntax = parse("void f(int a, [b = 1]) { a; }\n");
    let kinds: Vec<_> = syntax.sites.iter().map(|site| site.kind).collect();
    assert_eq!(
        kinds,
        [
            SiteKind::Binding,
            SiteKind::Type,
            SiteKind::Binding,
            SiteKind::Reference,
            SiteKind::Reference
        ]
    );
}

#[test]
fn a_field_after_a_method_takes_the_method_as_its_scope() {
    // The fallback of `_callable_context`: the first signature child of an ancestor that starts
    // before the node, here the method of the class body. A `method_signature` has no `name`
    // field, so the scope has no name, but the span and the depth of the method body.
    let syntax = parse("class A { void m() {} int x = y(); }\n");
    let call = syntax
        .sites
        .iter()
        .find(|site| site.kind == SiteKind::Call)
        .unwrap();
    assert_eq!(call.scope, None);
    assert_eq!(
        call.scope_span.as_ref().map(|span| span.start_byte),
        Some(19)
    );
    assert_eq!(call.scope_depth, 2);
}

#[test]
fn a_parameter_takes_the_scope_of_its_callable() {
    let syntax = parse("void f(int a, [b = 1]) { a; }\n");
    let bindings: Vec<_> = syntax
        .sites
        .iter()
        .filter(|site| site.kind == SiteKind::Binding)
        .collect();
    assert_eq!(bindings.len(), 2);
    for binding in bindings {
        assert_eq!(binding.scope.as_deref(), Some("f"));
        assert_eq!(binding.scope_depth, 2);
    }
}

#[test]
fn a_vertical_tab_around_the_equal_sign_is_a_plain_write() {
    // `bytes.strip` removes `\x0b`; `<[u8]>::trim_ascii` does not.
    let syntax = parse("void f() { x\u{b}=\u{b}1; y += 2; }\n");
    let uses: Vec<_> = syntax
        .sites
        .iter()
        .filter(|site| site.kind == SiteKind::Assignment)
        .map(|site| site.r#use)
        .collect();
    assert_eq!(uses, [SiteUse::Write, SiteUse::ReadWrite]);
}

#[test]
fn a_closure_marks_each_site_inside_it() {
    let syntax = parse("void f() { g(); var h = () { i(); }; }\n");
    let closures: Vec<_> = syntax
        .sites
        .iter()
        .filter(|site| site.kind == SiteKind::Call)
        .map(|site| (site.name.clone().unwrap_or_default(), site.closure_scope))
        .collect();
    assert_eq!(closures, [("g".to_owned(), false), ("i".to_owned(), true)]);
}

/// The work of `text` with an open limit.
fn work_of(text: &str) -> u64 {
    let mut parser = tree_sitter::Parser::new();
    parser
        .set_language(&archkeel_dart_grammar::LANGUAGE.into())
        .unwrap();
    let tree = parser.parse(text, None).unwrap();
    let source = Source::new(text.as_bytes());
    let work = Work::new(u64::MAX);
    sites(tree.root_node(), &source, &[], &[], &work).unwrap();
    work.spent()
}

#[test]
fn each_walk_and_each_scan_counts_its_work() {
    // The value pins the account: a walk, a scan or a copy that stops counting changes it. The
    // review of #1069 found a mutant that removed the charge of the walk and passed each test.
    let text = "class A { int f = 1; void m(B b) { b.c(d, e)..g; } }\nvar x = [a.b, c()];\n";
    assert_eq!(work_of(text), PINNED_WORK);
}

#[test]
fn the_work_grows_linearly_with_a_list_of_calls() {
    // Python scans the rest of the list for each element; the flags of `Family` read it once.
    let small = work_of(&format!("var x = [{}];\n", "f(), ".repeat(1_000)));
    let large = work_of(&format!("var x = [{}];\n", "f(), ".repeat(4_000)));
    assert!(large < small * 5, "{small} {large}");
}

#[test]
fn the_column_of_many_sites_on_one_line_is_read_once() {
    let args = |count: usize| {
        (0..count)
            .map(|i| format!("a{i}.b"))
            .collect::<Vec<_>>()
            .join(", ")
    };
    let small = work_of(&format!("void h() {{ g({}); }}\n", args(1_000)));
    let large = work_of(&format!("void h() {{ g({}); }}\n", args(4_000)));
    assert!(large < small * 5, "{small} {large}");
}
