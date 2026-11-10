// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the script facts. The layout that the walk records on the way down and up must equal
// the layout of a plain pass over the tree, for clean and for damaged sources.

use super::{Layout, NONE};
use crate::scan::scan;
use crate::source::Source;
use crate::syntax::Parsers;
use crate::tree::cx::Cx;
use crate::walk::Walk;

const SOURCES: [(&str, bool); 5] = [
    (
        "const a: Map<string, number> = x as Foo<T>; type U = typeof a;",
        true,
    ),
    (
        "class C extends B implements I { m(): void { f(() => 1); } }",
        true,
    ),
    (
        "function f(a, b) { return a satisfies T; } const { c } = d;",
        true,
    ),
    ("const x = (; function ) { } class { }", true),
    ("(function (w) { w.A = {}; })(window);", false),
];

/// The layout of the walk and the layout of a plain pass, for one source.
fn with_layouts(text: &str, typescript: bool, check: impl FnOnce(&Layout, &Layout)) {
    let mut parsers = Parsers::new();
    let data = text.as_bytes();
    let source = Source::new(data);
    let parsed = parsers.parse(typescript, data);
    assert!(parsed.is_some(), "{text}");
    let Some((tree, grammar)) = parsed else {
        return;
    };
    let cx = Cx {
        kinds: &grammar.map,
        source: &source,
    };
    let root = tree.root_node();
    let mut walk = Walk::new(cx);
    scan(&grammar.kinds, &source, root, &mut walk);
    check(&walk.take_layout(), &Layout::of(&cx, root));
}

#[test]
fn the_layout_of_the_walk_equals_the_layout_of_a_plain_pass() {
    for (text, typescript) in SOURCES {
        with_layouts(text, typescript, |walked, plain| {
            assert!(walked.nodes.len() > 3, "{text}");
            assert_eq!(walked.nodes, plain.nodes, "{text}");
            assert_eq!(walked.parents, plain.parents, "{text}");
            assert_eq!(walked.ends, plain.ends, "{text}");
            assert_eq!(walked.flags, plain.flags, "{text}");
            assert_eq!(walked.parents.first(), Some(&NONE));
        });
    }
}

#[test]
fn a_node_has_the_flags_of_its_parent_and_what_the_parent_adds() {
    with_layouts("function f(a: T) { return a; }", true, |layout, _| {
        let flag = |kind: &str, bit: u8| {
            let at = layout.nodes.iter().position(|node| node.kind() == kind);
            at.and_then(|at| layout.flags.get(at))
                .is_some_and(|flags| flags & bit != 0)
        };
        assert!(flag("return_statement", super::IN_FUNCTION));
        assert!(flag("type_identifier", super::IN_TYPE));
        assert!(!flag("return_statement", super::IN_TYPE));
    });
}

/// The flags of the first node of `kind` whose text is `text`.
fn flags_of(layout: &Layout, data: &[u8], kind: &str, text: &str) -> u8 {
    let found = layout.nodes.iter().position(|node| {
        node.kind() == kind && data.get(node.byte_range()) == Some(text.as_bytes())
    });
    assert!(found.is_some(), "{kind} {text}");
    found
        .and_then(|at| layout.flags.get(at).copied())
        .unwrap_or(0)
}

#[test]
fn a_node_below_a_repair_is_in_error_and_the_repair_itself_is_not() {
    let text = "const x = (; function ) { }";
    with_layouts(text, true, |layout, _| {
        let under = layout.nodes.iter().enumerate().filter(|(at, node)| {
            let up = layout.parents.get(*at).copied().unwrap_or(NONE);
            let parent = layout.nodes.get(up as usize).filter(|_| up != NONE);
            parent.is_some_and(|parent| parent.is_error()) && node.kind() != "ERROR"
        });
        let flags: Vec<u8> = under
            .filter_map(|(at, _)| layout.flags.get(at).copied())
            .collect();
        assert!(!flags.is_empty());
        assert!(flags.iter().all(|flags| flags & super::IN_ERROR != 0));
        let clean = layout.nodes.iter().position(|node| node.is_error());
        let root_flags = layout.flags.first().copied().unwrap_or(0);
        assert!(clean.is_some() && root_flags & super::IN_ERROR == 0);
    });
}

#[test]
fn only_what_follows_the_value_of_a_cast_is_a_type() {
    for operator in ["as", "satisfies"] {
        let text = format!("const v = value {operator} Foo;");
        with_layouts(&text, true, |layout, _| {
            let data = text.as_bytes();
            let value = flags_of(layout, data, "identifier", "value");
            let named = flags_of(layout, data, "type_identifier", "Foo");
            assert_eq!(
                value & super::IN_TYPE,
                0,
                "{operator}: the value is not a type"
            );
            assert_ne!(
                named & super::IN_TYPE,
                0,
                "{operator}: the name after it is"
            );
        });
    }
}
