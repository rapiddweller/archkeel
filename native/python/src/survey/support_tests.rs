// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the construct capabilities of the reply (AD-737). A `forbidden_construct` rule passes
// on an absence only when its construct is `supported`; each form that can hide a site must make
// the construct `partial`, also when one module of many has it.

use std::collections::BTreeSet;

use archkeel_facts::ConstructFact;

use super::{Construct, Seen, Support};
use crate::survey::targets::tests::surveyed;

/// The constructs whose support depends on the code: the run states them `supported` and each
/// module with a hiding form carries a gap (#1537), except `string_literal_compare`.
const PER_MODULE: [Construct; 12] = [
    Construct::BroadExcept,
    Construct::DunderDict,
    Construct::Vars,
    Construct::Getattr,
    Construct::Hasattr,
    Construct::Setattr,
    Construct::Delattr,
    Construct::Eval,
    Construct::Exec,
    Construct::Cast,
    Construct::DynamicImport,
    Construct::TypeIgnore,
];

#[test]
fn downgrade_and_meet_keep_the_worse_support_of_each_construct() {
    let start = Support::start();
    assert_eq!(start.of(Construct::Assert), Seen::Supported);
    assert_eq!(start.of(Construct::AnyAnnotation), Seen::Partial);
    for construct in PER_MODULE
        .into_iter()
        .chain([Construct::StringLiteralCompare])
    {
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
        let others = Construct::PER_MODULE
            .iter()
            .filter(|c| **c != construct && **c != Construct::Assert);
        assert!(others.into_iter().all(|c| left.of(*c) == Seen::Supported));
    }
}

#[test]
fn the_run_states_each_construct_of_a_module_supported() {
    let mut one = Support::start();
    one.downgrade(Construct::Cast);
    one.downgrade(Construct::StringLiteralCompare);
    let mut run = Support::start();
    run.meet(&one);
    run.settle();
    assert_eq!(run.of(Construct::Cast), Seen::Supported);
    // `string_literal_compare` stays run-wide: it needs the type of an operand.
    assert_eq!(run.of(Construct::StringLiteralCompare), Seen::Partial);
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
            "dynamic_import",
            "cast",
            "type_ignore",
            "placeholder_body",
            "hasattr",
            "setattr",
            "delattr",
            "eval",
            "exec"
        ]
    );
}

#[test]
fn a_protocol_receipt_does_not_claim_unconditional_support_on_the_wire() {
    let mut conditional = Support::start();
    conditional.observe_placeholder(super::PlaceholderCoverage::UsesProtocol);
    assert!(conditional.placeholder_under_premise());
    assert!(conditional
        .reply()
        .contains(&("placeholder_body", "partial")));
    let mut unread = Support::start();
    unread.downgrade(Construct::Placeholder);
    conditional.meet(&unread);
    assert!(!conditional.placeholder_under_premise());
}

/// The survey of a project with a clean module and one module with this source.
fn survey(source: &str) -> crate::survey::Survey {
    surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/clean.py", "value = 1\n"),
        ("src/app/page.py", source),
    ])
}

/// The constructs that an `unseen_form` record says can hide in `app.page`; no other module has one.
fn hidden(source: &str) -> BTreeSet<&'static str> {
    let found = survey(source);
    let mut words = BTreeSet::new();
    for record in &found.constructs {
        let ConstructFact::UnseenForm(data) = &record.data else {
            continue;
        };
        assert!(
            data.owner.split(':').next() == Some("app.page"),
            "only the module with the form has a record: {}",
            data.owner
        );
        let known = Construct::ALL
            .iter()
            .find(|c| c.word() == data.construct)
            .unwrap();
        words.insert(known.word());
    }
    words
}

type Forms = Vec<(Construct, &'static [&'static str])>;

/// The forms that can hide a builtin call, a dunder dict or an exception handler.
fn builtin_forms() -> Forms {
    vec![
        (
            Construct::BroadExcept,
            &[
                "try:\n    pass\nexcept ValueError:\n    pass\n",
                "E = Exception\ntry:\n    pass\nexcept E:\n    pass\n",
            ],
        ),
        (
            Construct::DunderDict,
            &[
                "value = getattr(item, '__dict__')\n",
                "value = table['__dict__']\n",
                "value = item.__getattribute__('__dict__')\n",
            ],
        ),
        (
            Construct::Vars,
            &[
                "f = vars\n",
                "vars = other\nvalue = vars(item)\n",
                "o = M.vars\n",
            ],
        ),
        (
            Construct::Getattr,
            &[
                "f = getattr\n",
                "getattr = other\nvalue = getattr(item, 'name')\n",
                "value = builtins.getattr(item, 'name')\n",
                "value = globals()['getattr'](item, 'name')\n",
            ],
        ),
        (
            Construct::Hasattr,
            &[
                "f = hasattr\n",
                "hasattr = other\nvalue = hasattr(item, 'name')\n",
                "import builtins\n",
                "value = eval('hasattr(item, 1)')\n",
                "name = fn.__globals__\n",
                "value = ns['__builtins__']\n",
                "value = find_class('builtins', 'hasattr')\n",
                "import builtins as b\n",
            ],
        ),
        (
            Construct::Setattr,
            &[
                "f = setattr\n",
                "value = vars(__builtins__)['setattr']\n",
                "value = getattr(mod, 'setattr')\n",
            ],
        ),
        (
            Construct::Delattr,
            &[
                "f = delattr\n",
                "x = o.delattr\n",
                "from builtins import delattr\n",
            ],
        ),
        (
            Construct::Eval,
            &["f = eval\n", "exec('value = eval(x)')\n", "g = compile\n"],
        ),
        (
            Construct::Exec,
            &["f = exec\n", "value = eval('exec(x)')\n", "o.exec(x)\n"],
        ),
    ]
}

/// The forms that can hide a cast, a loader or a type ignore.
fn module_forms() -> Forms {
    vec![
        (
            Construct::Cast,
            &[
                "from typing import cast as c\nf = c\n",
                "import typing\nf = typing.cast\n",
                "import typing\nf = typing\n",
                "from typing import *\n",
                "value = mod.cast(int, item)\n",
                "def f():\n    from typing import cast as k\n    return k(int, 1)\n",
                "cast = other\nvalue = cast(int, item)\n",
            ],
        ),
        (
            Construct::TypeIgnore,
            &[
                "import os  # type: ignore\n",
                "def f(a):  # type: ignore[arg-type]\n    return a\n",
            ],
        ),
        (
            Construct::DynamicImport,
            &[
                "import importlib\nf = importlib.import_module\n",
                "from importlib import import_module as m\nf = m\n",
                "f = __import__\n",
                "import importlib\nf = importlib\n",
                "from importlib import *\n",
                "value = mod.import_module('x')\n",
            ],
        ),
    ]
}

// Each form below can hide a site of its construct (the CLI plants in
// `tests/test_cli_python_profile_limits.py` run each one through Python and the rule stays
// UNKNOWN). The module that has it must carry an `unseen_form` record for the construct.
#[test]
fn each_form_that_can_hide_a_construct_is_a_record_of_its_module() {
    let cases: Forms = builtin_forms().into_iter().chain(module_forms()).collect();
    for (construct, sources) in cases {
        for source in sources {
            assert!(
                hidden(source).contains(construct.word()),
                "{construct:?}: {source}: {:?}",
                hidden(source)
            );
        }
    }
    let compare = survey("value = item in ('ready', 'done')\n");
    assert_eq!(
        compare.support.of(Construct::StringLiteralCompare),
        Seen::Partial
    );
}

#[test]
fn a_site_that_a_record_states_is_no_hidden_form_and_a_clean_module_has_no_gap() {
    for source in [
        "value = 1\n",
        "value = getattr(item, 'name')\n",
        "value = hasattr(item, 'name')\n",
        "setattr(item, 'name', 1)\ndelattr(item, 'name')\n",
        "value = vars(item)\n",
        "value = item.__dict__\n",
        "from typing import cast\nvalue = cast(int, item)\n",
        "import typing\nvalue = typing.cast(int, item)\nx: typing.Any = 1\n",
        "import importlib\nvalue = importlib.import_module('x')\n",
        "value = __import__('x')\n",
        "# The type of the value is a note.\nvalue = 1\n",
        // A name in a table of names is data: no lookup reads it here.
        "BANNED = {'__builtins__', 'eval', 'builtins'}\n",
        "GLOBALS = {'__builtins__': {}}\n",
        "import sys\nsys.modules['x'] = 1\n",
        "def refused(node):\n    return node.value == '__builtins__' or node.id in {'eval'}\n",
        "key = '__dict__'\n",
        "import ast\nvalue = ast.parse('x', mode='eval')\n",
    ] {
        let found = hidden(source);
        // `value = getattr(...)` and the like have no hiding form of their own.
        assert!(
            found.is_empty() || found == BTreeSet::from(["dunder_dict"]),
            "{source}: {found:?}"
        );
    }
}
