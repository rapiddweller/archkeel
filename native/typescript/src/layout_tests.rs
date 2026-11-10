// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the script facts. The layout that the walk records on the way down and up must equal
// the layout of a plain pass over the tree, for clean and for damaged sources.

use super::{Layout, NONE};
use crate::members::Cx;
use crate::scan::scan;
use crate::source::Source;
use crate::syntax::Parsers;
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
