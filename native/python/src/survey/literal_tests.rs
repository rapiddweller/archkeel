// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a proven call becomes an import record and loses its gap (AD-472). A neighbour form
// must keep a `dynamic_import` gap, so each one has a case. The cases run the hazard walk, so the
// exemption of the callee is checked too.

use super::super::hazards::{sites, DYNAMIC, LITERAL};
use super::*;

/// The kinds and texts of the sites of a module.
fn found(source: &str) -> Vec<(&'static str, String)> {
    let tree = crate::test_tree(source, 14).expect("valid probe");
    let proof = Proof::of(&tree, &Binders::of(&tree));
    sites(&tree, proof)
        .into_iter()
        .map(|site| (site.kind, site.detail))
        .collect()
}

#[test]
fn a_direct_unaliased_literal_call_is_a_static_edge_and_no_hazard() {
    for source in [
        "import importlib\nimportlib.import_module('app.service')\n",
        "import importlib\nload = lambda: importlib.import_module('app.service')\n",
        "import importlib\ndef later():\n    importlib.import_module('app.service')\n",
        "import importlib\nimport importlib\nimportlib.import_module('app.service')\n",
        "__import__('app.service')\n",
    ] {
        assert_eq!(
            found(source),
            [(LITERAL, "app.service".to_owned())],
            "{source}"
        );
    }
}

#[test]
fn each_neighbour_form_stays_a_dynamic_import() {
    for source in [
        "import importlib\nimportlib.import_module(name)\n",
        "import importlib\nimportlib.import_module(f'app.{name}')\n",
        "import importlib\nimportlib.import_module('app.' 'service')\n",
        "import importlib\nimportlib.import_module('.service', 'app')\n",
        "import importlib\nimportlib.import_module('.service')\n",
        "import importlib\nimportlib.import_module('app.service', package='app')\n",
        "import importlib\nimportlib.import_module('app service')\n",
        "__import__('app.service', globals(), None, ['x'])\n",
        "import importlib as il\nil.import_module('app.service')\n",
        "import importlib.util\nimportlib.import_module('app.service')\n",
        "from importlib import import_module\nimport_module('app.service')\n",
        "import importlib\nimportlib = other\nimportlib.import_module('app.service')\n",
        "import importlib\ndef f(importlib):\n    importlib.import_module('app.service')\n",
        "import importlib\nfor importlib in items:\n    importlib.import_module('app.service')\n",
        "import importlib\ndef f():\n    global importlib\nimportlib.import_module('app.service')\n",
        "import importlib\nfrom tools import *\nimportlib.import_module('app.service')\n",
        "import importlib\nvars()\nimportlib.import_module('app.service')\n",
        "importlib.import_module('app.service')\n",
        "__import__ = hook\n__import__('app.service')\n",
        "def __import__(name):\n    return name\n__import__('app.service')\n",
        "import importlib\nload = importlib.import_module\nload('app.service')\n",
        "import importlib\ngetattr(importlib, 'import_module')('app.service')\n",
        "import importlib\nother.import_module('app.service')\n",
    ] {
        let kinds: Vec<&str> = found(source).into_iter().map(|(kind, _)| kind).collect();
        assert!(kinds.contains(&DYNAMIC), "{source}: {kinds:?}");
        assert!(!kinds.contains(&LITERAL), "{source}: {kinds:?}");
    }
}

#[test]
fn a_proven_call_exempts_only_its_own_callee() {
    let source = "import importlib\nimportlib.import_module('app.a')\nx = importlib.reload\n";
    let kinds: Vec<&str> = found(source).into_iter().map(|(kind, _)| kind).collect();
    assert_eq!(kinds, [LITERAL, DYNAMIC]);
}

#[test]
fn a_door_in_any_position_other_than_the_exempt_callee_is_a_gap() {
    for source in [
        "__import__.__call__('app.service')\n",
        "exec.__call__('import app.service')\n",
        "eval.__call__('x')\n",
        "compile.__call__(text, 'f', 'exec')\n",
        "__import__.__self__.__dict__['__import__']('app.service')\n",
        "import importlib\nimportlib.__dict__['import_module']('app.service')\n",
        "import importlib\nimportlib.__getattribute__('import_module')('app.service')\n",
        "import importlib\nvars(importlib)['import_module']('app.service')\n",
        "import importlib\ntype(importlib).__getattribute__(importlib, 'import_module')\n",
        "import importlib\nuse(importlib)\n",
        "import importlib\nitems = [importlib]\n",
        "import importlib\nimportlib.import_module.__call__('app.service')\n",
        "import builtins\nbuiltins.__dict__['__import__']('app.service')\n",
        "__builtins__['__import__']('app.service')\n",
        "__builtins__.__import__('app.service')\n",
        "import sys\nsys.modules['builtins'].__import__('app.service')\n",
        "globals()['__import__']('app.service')\n",
        "locals()['__builtins__']\n",
        "vars()['__builtins__']\n",
        "len.__self__.__import__('app.service')\n",
        "handler.__globals__['__builtins__']\n",
        "().__class__.__base__.__subclasses__()\n",
        "__loader__.load_module('app.service')\n",
        "loader = __spec__.loader\n",
        "getattr(thing, '__import__')('app.service')\n",
        "breakpoint()\n",
        "import sys\nsys.__getattribute__('modules')\n",
        "names = vars()\n",
        "owner = len.__self__\n",
        "names = globals()\n",
        "names = locals()\n",
    ] {
        let kinds: Vec<&str> = found(source).into_iter().map(|(kind, _)| kind).collect();
        assert!(
            kinds.iter().any(|kind| *kind != LITERAL),
            "{source}: {kinds:?}"
        );
    }
    let exact = "import importlib\nimportlib.import_module('app.service')\n";
    assert_eq!(found(exact), [(LITERAL, "app.service".to_owned())]);
}

#[test]
fn a_locals_call_proves_nothing() {
    let source = "import importlib\nlocals()\nimportlib.import_module('app.service')\n";
    let kinds: Vec<&str> = found(source).into_iter().map(|(kind, _)| kind).collect();
    assert!(!kinds.contains(&LITERAL), "{kinds:?}");
}
