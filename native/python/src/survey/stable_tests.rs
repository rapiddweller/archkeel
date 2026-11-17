// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::module::EvidenceMap;
use crate::survey::imports;

#[test]
fn class_inventory_proof_is_absent_when_a_class_or_namespace_can_be_hidden() {
    for source in [
        "",
        "\"\"\"Module.\"\"\"\nfrom __future__ import annotations\nfrom x import y\ndef test(a: T):\n    assert a.value() == 1\n",
    ] {
        let tree = crate::test_tree(source, 12).unwrap();
        assert!(super::class_inventory::empty(&tree), "{source}");
    }
    for source in [
        "class A: pass\n",
        "if flag:\n    class A: pass\n",
        "def f():\n    class A: pass\n",
        "from x import *\n",
        "A = type('A', (), {})\n",
        "def f():\n    global A\n    A = factory()\n",
        "def f():\n    globals()['A'] = factory()\n",
        "@factory\ndef f(): pass\n",
        "def f(x=factory()): pass\n",
        "def __getattr__(name): return factory(name)\n",
    ] {
        let tree = crate::test_tree(source, 12).unwrap();
        assert!(!super::class_inventory::empty(&tree), "{source}");
    }
}

#[test]
fn empty_class_inventory_is_written_on_its_module_file() {
    let survey = crate::survey::targets::tests::surveyed(&[
        ("src/app/empty.py", "def f():\n    return 1\n"),
        ("src/app/unread.py", "@decorator\nclass A: pass\n"),
    ]);
    let file = |name: &str| {
        survey
            .files
            .iter()
            .find(|file| file.module.as_str() == name)
            .unwrap()
    };
    assert_eq!(file("app.empty").class_inventory_empty, Some(true));
    assert_eq!(file("app.unread").class_inventory_empty, None);
    assert_eq!(
        serde_json::to_value(file("app.empty")).unwrap()["class_inventory_empty"],
        true
    );
    assert!(serde_json::to_value(file("app.unread"))
        .unwrap()
        .get("class_inventory_empty")
        .is_none());
    let changed = crate::survey::targets::tests::surveyed(&[
        ("src/app/empty.py", "def f():\n    return 1\n"),
        (
            "src/app/writer.py",
            "import app.empty\napp.empty.X = value\n",
        ),
    ]);
    assert!(changed
        .files
        .iter()
        .all(|file| file.class_inventory_empty.is_none()));
    let support = crate::survey::targets::tests::surveyed(&[
        ("src/app/test.py", "from __future__ import annotations\nfrom app.support import Builder\ndef test():\n    assert Builder().valid()\n"),
        ("src/app/support.py", "from dataclasses import dataclass\n@dataclass\nclass Builder:\n    value: int\n"),
    ]);
    assert_eq!(
        support
            .files
            .iter()
            .find(|file| file.module.as_str() == "app.test")
            .unwrap()
            .class_inventory_empty,
        Some(true)
    );
}

#[test]
fn architecture_test_suites_have_empty_class_inventory_outside_support() {
    let files = [
        (
            "tests/__init__.py",
            include_str!("../../../../fixtures/F-architecture/tests/__init__.py"),
        ),
        (
            "tests/unit/__init__.py",
            include_str!("../../../../fixtures/F-architecture/tests/unit/__init__.py"),
        ),
        (
            "tests/unit/test_entities.py",
            include_str!("../../../../fixtures/F-architecture/tests/unit/test_entities.py"),
        ),
        (
            "tests/integration/__init__.py",
            include_str!("../../../../fixtures/F-architecture/tests/integration/__init__.py"),
        ),
        (
            "tests/integration/test_place_order.py",
            include_str!(
                "../../../../fixtures/F-architecture/tests/integration/test_place_order.py"
            ),
        ),
        (
            "tests/support/__init__.py",
            include_str!("../../../../fixtures/F-architecture/tests/support/__init__.py"),
        ),
        (
            "tests/support/orders.py",
            include_str!("../../../../fixtures/F-architecture/tests/support/orders.py"),
        ),
    ];
    let survey = crate::survey::targets::tests::surveyed_in(&files, &["tests"], "tests");
    for file in &survey.files {
        if !file.module.as_str().starts_with("tests.support") {
            assert_eq!(
                file.class_inventory_empty,
                Some(true),
                "{}",
                file.module.as_str()
            );
        }
    }
}

/// The stable bindings of `app/__init__.py` beside the empty modules `app.sib` and `app.sub`.
fn stable(text: &str, minor: u32) -> Vec<String> {
    let files = [
        ("src/app/__init__.py", "app", text),
        ("src/app/sib.py", "app.sib", ""),
        ("src/app/sub.py", "app.sub", ""),
    ];
    let modules: Vec<Module> = files
        .iter()
        .map(|(rel, name, text)| {
            let tree = crate::test_tree(text, minor).expect("valid source");
            Module::new(
                (*rel).to_owned(),
                (*name).to_owned(),
                (*text).to_owned(),
                tree,
            )
        })
        .collect();
    let binders: Vec<Binders> = modules
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let mut evidence = EvidenceMap::new();
    let (_, aliases) = imports::collect(&modules, &binders, "app", &mut evidence);
    bindings(
        &modules[0],
        &binders[0],
        &aliases[0],
        crate::test_minor(minor),
    )
}

/// Each source with the `stable_direct_module_bindings` of the Python collector after
/// `collect_imports` on CPython 3.12. The first cases are `READS` of
/// the deleted `tests/test_loader_exposure_scope.py` behind `import importlib`.
const CASES: &[(&str, &[&str])] = &[
    ("import importlib\nset(globals())\n", &["importlib"]),
    ("import importlib\nfrozenset(globals())\n", &["importlib"]),
    ("import importlib\nsorted(globals())\n", &["importlib"]),
    ("import importlib\nlist(globals())\n", &["importlib"]),
    ("import importlib\ntuple(globals())\n", &["importlib"]),
    ("import importlib\nsorted(set(globals()))\n", &["importlib"]),
    ("import importlib\nlist(globals().keys())\n", &["importlib"]),
    ("import importlib\n'x' in globals()\n", &["importlib"]),
    ("import importlib\n'x' not in globals()\n", &["importlib"]),
    ("import importlib\nlen(globals())\n", &["importlib"]),
    ("import importlib\n[k for k in globals()]\n", &["importlib"]),
    ("import importlib\nfor k in globals(): pass\n", &["importlib"]),
    ("import importlib\ng = globals()\n", &[]),
    ("import importlib\nglobals()['importlib']\n", &[]),
    ("import importlib\nglobals().get('x')\n", &[]),
    ("import importlib\ndict(globals())\n", &[]),
    ("import importlib\nlist(globals().items())\n", &[]),
    ("import importlib\nlist(globals().values())\n", &[]),
    ("import importlib\nf(globals())\n", &[]),
    ("import importlib\nglobals().update(x=1)\n", &[]),
    ("import importlib\nglobals()['a'] = 1\n", &[]),
    ("import importlib\nx == globals()\n", &[]),
    ("import importlib\nglobals() in x\n", &[]),
    ("import importlib\nf = globals().keys\n", &[]),
    ("import importlib\nsorted([], key=globals())\n", &[]),
    ("import importlib\n[k for k in x if globals()]\n", &[]),
    ("import importlib\nglobals()(1)\n", &[]),
    ("import importlib\nx in globals() == y\n", &[]),
    ("import importlib\n'x' in globals() in y\n", &[]),
    ("import importlib\n'x' not in globals() in y\n", &[]),
    ("import importlib\n'x' in globals() not in y\n", &[]),
    ("import importlib\n'x' in globals().keys() in y\n", &[]),
    ("import importlib\nglobals() in x in y\n", &[]),
    ("import importlib\nx is globals()\n", &[]),
    ("import importlib\nx < globals()\n", &[]),
    ("import importlib\nx in globals() in y in z\n", &[]),
    ("import importlib\nx in y in globals()\n", &["importlib"]),
    ("import importlib\nx == y in globals()\n", &["importlib"]),
    ("import importlib\nx not in y not in globals()\n", &["importlib"]),
    ("import importlib\nx in y in z in globals()\n", &["importlib"]),
    ("import importlib\nx in y in globals().keys()\n", &["importlib"]),
    ("import importlib\nset(globals().keys())\n", &["importlib"]),
    ("import importlib\n'x' in globals().keys()\n", &["importlib"]),
    ("import importlib\nfor k in globals().keys(): pass\n", &["importlib"]),
    ("import importlib\nsorted(globals(), key=len)\n", &["importlib"]),
    ("import importlib\nk = globals().keys()\n", &[]),
    ("import importlib\nglobals().keys().mapping['importlib']\n", &[]),
    ("import importlib\nglobals().keys() & x\n", &[]),
    ("import importlib\nset(x, globals())\n", &[]),
    ("import importlib\ndef set(ns): pass\nset(globals())\n", &[]),
    ("import importlib\nset = f\nset(globals())\n", &[]),
    ("import importlib\nimport set\nset(globals())\n", &[]),
    ("import importlib\nfrom m import sorted\nsorted(globals())\n", &[]),
    ("import importlib\nclass list: pass\nlist(globals())\n", &[]),
    ("import importlib\ndef f(len): return len(globals())\n", &[]),
    ("import importlib\nbuiltins.set(globals())\n", &[]),
    ("import importlib\nkeys = set(globals())\n", &["importlib", "keys"]),
    ("import importlib\nnames = globals()\n", &[]),
    ("import importlib\nnames = vars(importlib)\n", &[]),
    ("import importlib\nkeys = set(locals())\n", &[]),
    ("import importlib\n__import__(\"json\")\n", &[]),
    ("import os\nimport a.b\nfrom x import y as z\ndef f(p): pass\nclass C: pass\nv = 1\nw: int\n", &["C", "a", "f", "os", "v", "w", "z"]),
    ("x = 1\nx = 2\ny, (z, *t) = 1, (2, 3)\n", &["t", "y", "z"]),
    ("a = 1\nif c:\n    a = 2\nb = 1\ndef g():\n    b = 2\n", &["b", "g"]),
    ("a = 1\ndef g():\n    global a\n", &["g"]),
    ("from m import *\na = 1\n", &[]),
    ("def f():\n    from m import *\na = 1\n", &["a", "f"]),
    ("a = 1\nexec('a = 2')\n", &[]),
    ("import builtins as b\nx = 1\nb.eval('1')\n", &[]),
    ("from builtins import eval as e\nx = 1\ndef f():\n    e\n", &[]),
    ("x = 1\ndef f():\n    from builtins import eval as e\n    e\n", &["f", "x"]),
    ("x = 1\ng = globals\n", &[]),
    ("x = 1\ndef f():\n    return locals()\n", &["f", "x"]),
    ("x = 1\nlocals()\n", &[]),
    ("x = 1\nprint(vars)\n", &[]),
    ("x = 1\nclass C(vars): pass\n", &[]),
    ("x = 1\ndef f(a=locals()): pass\n", &[]),
    ("import pkg\nfrom pkg import y\nfrom pkg import sub as s\nz = 1\npkg.attr = 1\n", &["z"]),
    ("import pkg.mod as m\nfrom pkg.mod import y\nfrom pkg import q\nm.attr = 1\n", &["q"]),
    ("import pkg\nimport pkg.mod\nfrom pkg import y\nk = 1\ndef f():\n    import pkg\n    pkg.x = 1\n", &["f", "k"]),
    ("class A: pass\nB = A\nC = B\nD = 1\nC.x = 1\n", &["D"]),
    ("class A: pass\nB: type = A\nB.x = 1\nE = 1\n", &["E"]),
    ("a = 1\nb = 2\nc = [1]\nc[a].x = 1\nf(b).y = 1\n", &["b"]),
    ("a = 1\nb = 2\nx = [1]\nx[lambda q: b].y = 1\n", &["a"]),
    ("a = 1\nb = 2\ndel a.z\n", &["b"]),
    ("a = 1\nb = 2\nfor a.z in r: pass\n", &["b"]),
    ("a = 1\nx = [1]\nx[lambda a: 0] = 1\n", &["x"]),
    ("x = [1]\nx[(n := 1)] = 2\nm = 3\n", &["m", "n", "x"]),
    ("x = [1]\nx[[i for i in r]] = 2\ni = 1\n", &["x"]),
    ("type T = int\nu = 1\n", &["T", "u"]),
    ("type T[X] = list[X]\nu = 1\n", &["u"]),
    ("def f[T](a: T) -> T: return a\nu = 1\n", &["f", "u"]),
    ("u = [y := 1 for _ in r]\nv = 1\n", &["u", "v"]),
    ("u = [(y := 1) for _ in r]\ny = 2\n", &["u"]),
    ("try:\n    import j\nexcept E as j:\n    pass\nk = 1\n", &["k"]),
    ("match v:\n    case [*s]: pass\n    case {**r}: pass\n    case q: pass\ns = 1\nr = 1\nq = 1\nw = 1\n", &["w"]),
    ("import importlib\nif 'x' in globals().keys(): pass\n", &["importlib"]),
    ("import importlib\nwhile globals(): pass\n", &[]),
    ("import importlib\nset(*globals())\n", &[]),
    ("import importlib\nlen(globals(), k=1)\n", &["importlib"]),
    ("import importlib\nclass C:\n    globals()\n", &[]),
    ("a = 1\nb = a\nb.x = 1\nc = 1\n", &["c"]),
    ("a = 1\ndef f():\n    b = a\n    b.x = 1\nc = 1\n", &["c", "f"]),
    ("import os\nos.environ.x = 1\nfrom os import path\nfrom os.path import join\nk = 1\n", &["join", "k"]),
    ("from . import sib\nsib.x = 1\nfrom .sib import t\nk = 1\n", &["k", "t"]),
    ("import a.b.c\na.q = 1\nfrom a import d\nfrom a.b import e\nk = 1\n", &["e", "k"]),
    ("x = 1\nx += 1\ny = 1\n", &["y"]),
    ("x = 1\nwith c as x: pass\ny = 1\n", &["y"]),
    ("x = 1\nimport x\ny = 1\n", &["y"]),
    ("x = 1\n@globals\ndef f(): pass\n", &[]),
    ("x = 1\nf'{globals()}'\n", &[]),
];

#[test]
fn each_case_has_the_stable_bindings_of_python() {
    for (text, expected) in CASES {
        assert_eq!(stable(text, 12), *expected, "{text:?}");
    }
}

#[test]
fn a_type_alias_is_a_direct_binding_from_python_3_12() {
    assert_eq!(stable("type T = int\nu = 1\n", 13), ["T", "u"]);
    assert_eq!(stable("u = 1\n", 11), ["u"]);
}

#[test]
fn a_call_that_can_create_a_class_names_its_callee_and_withholds_the_receipt() {
    // #1713: a factory by its import, `type` with three arguments, a metaclass shape, and a call
    // result used as a class.
    for (source, callee) in [
        (
            "from enum import Enum\ndef f():\n    return Enum('C', 'A')\n",
            "enum.Enum",
        ),
        (
            "import enum as e\ndef f():\n    return e.Flag('C', 'A')\n",
            "enum.Flag",
        ),
        (
            "import collections\ndef f():\n    return collections.namedtuple('P', 'x')\n",
            "collections.namedtuple",
        ),
        (
            "def f():\n    return __build_class__(lambda: None, 'C')\n",
            "builtins.__build_class__",
        ),
        ("def f():\n    return type('C', (), {})\n", "builtins.type"),
        ("def f(m):\n    return m('C', (), {})\n", "a metaclass call"),
        (
            "def f(g):\n    made = g()\n    return made()\n",
            "a call result used as a class",
        ),
        (
            "def f(x, g):\n    return issubclass(x, g())\n",
            "a call result used as a class",
        ),
    ] {
        let tree = crate::test_tree(source, 12).unwrap();
        let site = super::class_inventory::factory_site(&tree).map(|(_, callee)| callee);
        assert_eq!(site.as_deref(), Some(callee), "{source}");
        assert!(!super::class_inventory::empty(&tree), "{source}");
    }
    for source in [
        "def f(x):\n    return type(x)\n",
        "def f(cb, items):\n    return cb(len(items))\n",
        "from enum import Enum\ndef f(x):\n    return isinstance(x, Enum)\n",
    ] {
        let tree = crate::test_tree(source, 12).unwrap();
        assert!(
            super::class_inventory::factory_site(&tree).is_none(),
            "{source}"
        );
    }
}
