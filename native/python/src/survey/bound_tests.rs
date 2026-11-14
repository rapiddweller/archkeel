// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the proof of a re-export (`routes.rs`) and the package shadow rule read one function
// of the names that a module body may bind (AD-504). A name has a sole plain binder only when one
// `def`, `class`, `import` or `name = value` directly in the module body binds it.

use ruff_text_size::Ranged;

use super::*;

fn bound(source: &str) -> (Bound, Vec<ruff_python_ast::Stmt>) {
    let tree = crate::test_tree(source, 13).expect("valid source");
    (Bound::of(&tree.body), tree.body.to_vec())
}

/// Whether the first statement of the body is the sole plain binder of `name`.
fn sole(source: &str, name: &str) -> bool {
    let (found, body) = bound(source);
    body.first()
        .is_some_and(|first| found.sole(name, first.range().start()))
}

#[test]
fn a_plain_statement_of_the_module_body_is_the_sole_binder() {
    for source in [
        "from app.pub import f\n",
        "import app.pub as f\n",
        "def f(): pass\n",
        "class f: pass\n",
        "f = 1\n",
        "f: int = 1\n",
    ] {
        assert!(sole(source, "f"), "{source}");
    }
}

#[test]
fn each_other_binder_of_the_name_makes_it_ambiguous() {
    for source in [
        // a second binder, in each form
        "from app.pub import f\ndef f(): pass\n",
        "from app.pub import f\nf = 1\n",
        "from app.pub import f\nf += 1\n",
        "from app.pub import f\ndel f\n",
        "from app.pub import f\nfor f in []: pass\n",
        "from app.pub import f\nwith open('x') as f: pass\n",
        "from app.pub import f\n(f, g) = (1, 2)\n",
        "from app.pub import f\n(f := 1)\n",
        "from app.pub import f\ntry:\n    pass\nexcept OSError as f:\n    pass\n",
        "from app.pub import f\nmatch 1:\n    case f:\n        pass\n",
        "from app.pub import f\nfrom app.other import f\n",
        // a function that declares the name global
        "from app.pub import f\ndef _go():\n    global f\n    f = 1\n",
        // a star import binds names that cannot be listed
        "from app.pub import f\nfrom app.other import *\n",
    ] {
        assert!(!sole(source, "f"), "{source}");
    }
}

#[test]
fn a_statement_in_a_compound_statement_is_no_plain_binder() {
    for source in [
        "try:\n    from app.pub import f\nexcept ImportError:\n    f = None\n",
        "if True:\n    from app.pub import f\n",
        "try:\n    from app.pub import f\nexcept ImportError:\n    pass\n",
    ] {
        let (found, body) = bound(source);
        let start = body[0].range().start();
        assert!(!found.sole("f", start), "{source}");
    }
}

#[test]
fn a_binder_in_a_function_or_a_class_binds_no_module_name() {
    let (found, body) = bound(
        "from app.pub import f\ndef _lazy():\n    from app.other import f\n    f = 1\nclass C:\n    f = 2\n",
    );
    assert!(found.sole("f", body[0].range().start()));
    let names = found.names();
    assert!(names.contains("f") && names.contains("_lazy") && names.contains("C"));
}

#[test]
fn a_package_body_that_binds_a_name_in_any_form_shadows_the_submodule() {
    for source in [
        "try:\n    from app.lib import _native as speedups\nexcept ImportError:\n    from app.lib import _pure as speedups\n",
        "for speedups in []: pass\n",
        "with open('x') as speedups: pass\n",
        "(speedups, other) = (1, 2)\n",
        "(speedups := 1)\n",
        "def _go():\n    global speedups\n    speedups = 1\n",
        "def speedups(): pass\n",
    ] {
        let (found, _) = bound(source);
        assert!(found.names().contains("speedups"), "{source}");
    }
}
