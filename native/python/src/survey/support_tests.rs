// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the construct capabilities of the reply (AD-737). A `forbidden_construct` rule passes
// on an absence only when its construct is `supported`; each form that can hide a site must make
// the construct `partial`, also when one module of many has it.

use super::{Construct, Seen, Support};
use crate::survey::targets::tests::surveyed;

/// The constructs whose support depends on the code.
const READ: [Construct; 5] = [
    Construct::BroadExcept,
    Construct::DunderDict,
    Construct::Vars,
    Construct::StringLiteralCompare,
    Construct::Getattr,
];

#[test]
fn downgrade_and_meet_keep_the_worse_support_of_each_construct() {
    let start = Support::start();
    assert_eq!(start.of(Construct::Assert), Seen::Supported);
    assert_eq!(start.of(Construct::AnyAnnotation), Seen::Partial);
    assert_eq!(start.of(Construct::DynamicImport), Seen::Partial);
    for construct in READ {
        assert_eq!(start.of(construct), Seen::Supported, "{construct:?}");
        let mut one = Support::start();
        one.downgrade(construct);
        assert_eq!(one.of(construct), Seen::Partial);
        // The meet is the worse of both, in either order.
        let mut left = Support::start();
        left.meet(&one);
        let mut right = one.clone();
        right.meet(&Support::start());
        assert_eq!(left, right);
        assert_eq!(left.of(construct), Seen::Partial);
        let others = READ.iter().filter(|c| **c != construct);
        assert!(others.into_iter().all(|c| left.of(*c) == Seen::Supported));
    }
}

#[test]
fn the_reply_lists_each_construct_once_in_its_order() {
    let words: Vec<&str> = Support::start().reply().iter().map(|(w, _)| *w).collect();
    assert_eq!(
        words,
        [
            "assert",
            "broad_except",
            "dunder_dict",
            "vars",
            "string_literal_compare",
            "getattr",
            "any_annotation",
            "dynamic_import"
        ]
    );
}

/// The support of the survey of a project with a clean module and one module with this source.
fn support(source: &str) -> Support {
    surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/clean.py", "value = 1\n"),
        ("src/app/page.py", source),
    ])
    .support
}

// Each form below can hide a site of its construct (the CLI plants in
// `tests/test_cli_python_profile_limits.py` run each one through Python and the rule stays
// UNKNOWN). The survey must state the construct `partial`.
#[test]
fn each_form_that_can_hide_a_construct_makes_it_partial() {
    let cases: [(Construct, &[&str]); 5] = [
        (
            Construct::BroadExcept,
            &[
                "try:\n    pass\nexcept ValueError:\n    pass\n",
                "E = Exception\ntry:\n    pass\nexcept E:\n    pass\n",
            ],
        ),
        (
            Construct::DunderDict,
            &["value = getattr(item, '__dict__')\n", "value = f(item)\n"],
        ),
        (
            Construct::Vars,
            &["f = vars\n", "vars = other\nvalue = vars(item)\n"],
        ),
        (
            Construct::StringLiteralCompare,
            &[
                "value = item in ('ready', 'done')\n",
                "predicate = item.startswith\n",
                "match item:\n    case 'ready': pass\n",
            ],
        ),
        (
            Construct::Getattr,
            &[
                "f = getattr\n",
                "getattr = other\nvalue = getattr(item, 'name')\n",
            ],
        ),
    ];
    for (construct, sources) in cases {
        for source in sources {
            assert_eq!(
                support(source).of(construct),
                Seen::Partial,
                "{construct:?}: {source}"
            );
        }
    }
}

#[test]
fn code_without_a_hiding_form_keeps_each_read_construct_supported() {
    let found = support("value = 1\n");
    for construct in READ {
        assert_eq!(found.of(construct), Seen::Supported, "{construct:?}");
    }
    assert_eq!(found.of(Construct::AnyAnnotation), Seen::Partial);
    assert_eq!(found.of(Construct::DynamicImport), Seen::Partial);
}
