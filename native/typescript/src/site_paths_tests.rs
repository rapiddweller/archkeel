// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the sites of a file. A path is the list of the names of a chain of members.

use super::{is_script_root, Text};

#[test]
fn frame_roots_extend_only_dependency_roots() {
    for name in ["top", "parent"] {
        assert!(crate::script_deps::is_root(name));
        assert!(!is_script_root(name.as_bytes()));
        assert!(!crate::script_scope::is_root(name));
    }
    for name in crate::source_input::WALK_ROOTS {
        assert!(is_script_root(name.as_bytes()));
        assert!(crate::script_scope::is_root(name));
        assert!(crate::script_deps::is_root(name));
    }
    assert!(!crate::script_deps::is_root("global"));
}
use crate::parse::parse;
use crate::syntax::Parsers;

fn paths(source: &str) -> Vec<String> {
    let syntax = parse(&mut Parsers::new(), "a.ts", source.as_bytes()).syntax;
    syntax
        .sites
        .sites
        .iter()
        .map(|site| {
            site.path
                .map(|path| syntax.sites.paths.names(path, source.as_bytes()).join("."))
                .unwrap_or_default()
        })
        .collect()
}

#[test]
fn a_chain_of_plain_names_has_a_path_and_a_chain_with_a_call_has_none() {
    assert_eq!(paths("a.b.c();"), ["a.b.c"]);
    // The call of `a().b.c` finds its receiver `a()`, which has no path; `a` is a callee too.
    assert_eq!(paths("a().b.c();"), ["", "a"]);
    // A subscript has no path, but its object does: the call takes the path of its receiver.
    assert_eq!(paths("a['k'].b();"), ["a"]);
    assert_eq!(paths("(a.b)();"), ["a.b", "a", "a.b"]);
}

#[test]
fn a_text_is_cut_from_the_file_with_the_replacement_of_bad_bytes() {
    let data = b"ab\xffcd";
    assert_eq!(Text { start: 1, end: 4 }.decode(data), "b\u{fffd}c");
    assert_eq!(Text { start: 3, end: 3 }.decode(data), "");
    assert!(Text { start: 3, end: 3 }.is_empty());
    assert_eq!(Text { start: 9, end: 12 }.decode(data), "");
}

#[test]
fn only_the_names_of_the_global_object_are_roots() {
    assert!(
        is_script_root(b"window")
            && is_script_root(b"globalThis")
            && is_script_root(b"self")
            && is_script_root(b"frames")
    );
    assert!(!is_script_root(b"global") && !is_script_root(b"Window"));
}

#[test]
fn a_long_chain_costs_one_item_for_each_member() {
    let source = format!("a{}.z();", ".b".repeat(20_000));
    let syntax = parse(&mut Parsers::new(), "a.ts", source.as_bytes()).syntax;
    let path = syntax.sites.sites.first().and_then(|site| site.path);
    let names = path.map(|path| syntax.sites.paths.names(path, source.as_bytes()));
    assert_eq!(names.as_ref().map(Vec::len), Some(20_002));
    assert_eq!(
        path.map(|path| syntax.sites.paths.length(path)),
        Some(20_002)
    );
}
