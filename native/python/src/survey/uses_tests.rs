// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a route through a module is proven only for the namespace that the module builds
// (AD-504). Each use of a module binding that is not a direct attribute load escapes it; the
// survey then names the module and each module below it, and writes no route through them.

use crate::survey::targets::tests::surveyed;

/// The modules that the survey cannot prove a route through, for a writer module.
fn named(writer: &str) -> Vec<String> {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/lib.py", "def f(): pass\n__all__ = ['f']\n"),
        ("src/app/other.py", "VALUE = 1\n"),
        ("src/app/dyn.py", "DYN = build()\ndef build(): pass\n"),
        (
            "src/app/kinds.py",
            "import json\nfrom os import path as P\nfrom app.other import VALUE as V\n\
             NUMBER = 1\nTEXT = 'a'\nPAIR = (1, 2)\nTUPLE = tuple(PAIR)\nCOPY = NUMBER\n\
             CHAIN = V\nEXT = json.dumps\nMOD = P\nTWICE = 1\nTWICE = build()\n\
             LISTED = [build()]\nTYPES = {int: str, list: tuple}\nKEYS = tuple(TYPES.keys())\n\
             def build(): pass\n",
        ),
        ("src/app/writer.py", writer),
    ]);
    let mut names: Vec<String> = found.opaque_surface.into_iter().collect();
    names.sort();
    names
}

const LIB: [&str; 1] = ["app.lib"];

#[test]
fn each_write_to_a_module_of_the_scan_escapes_it() {
    let prefix = "from app import lib\n";
    for write in [
        "lib.f = 1\n",
        "lib.run = 1\n",
        "lib.f += 1\n",
        "del lib.f\n",
        "setattr(lib, 'f', 1)\n",
        "delattr(lib, 'f')\n",
        "lib.__all__ = []\n",
        "lib.__all__.remove('f')\n",
        "lib.__all__[0] = 'g'\n",
        "lib.__dict__['f'] = 1\n",
        "lib.__setattr__('f', 1)\n",
        "vars(lib)['f'] = 1\n",
        "(lib.f, other) = (1, 2)\n",
        "_l = [0 for lib.f in [1]]\n",
    ] {
        assert_eq!(named(&format!("{prefix}{write}")), LIB, "{write}");
    }
}

#[test]
fn a_binding_that_escapes_withholds_the_module() {
    let prefix = "from app import lib\n";
    for use_ in [
        "m = lib\nm.f = 1\n",
        "def patch(m):\n    m.f = 1\npatch(lib)\n",
        "class H:\n    m = lib\nH.m.f = 1\n",
        "[lib][0].f = 1\n",
        "(lib if True else lib).f = 1\n",
        "(m := lib).f = 1\n",
        "d = lib.__dict__\nd['f'] = 1\n",
        "names = lib.__all__\nnames.remove('f')\n",
        "getattr(lib, '__all__').remove('f')\n",
        "put = setattr\nput(lib, 'f', 1)\n",
        "import functools\nfunctools.partial(setattr, lib)('f', 1)\n",
        "def pick():\n    return lib\n",
    ] {
        assert_eq!(named(&format!("{prefix}{use_}")), LIB, "{use_}");
    }
}

#[test]
fn a_write_through_each_import_form_escapes_the_module() {
    for source in [
        "import app.lib\napp.lib.f = 1\n",
        "import app.lib as lib\nlib.f = 1\n",
        "from app import lib as moved\nmoved.f = 1\n",
        "def go():\n    from app import lib\n    lib.f = 1\n",
        "import importlib\nimportlib.import_module('app.lib').f = 1\n",
        "__import__('app.lib').f = 1\n",
        "from app.lib import __dict__ as d\nd['f'] = 1\n",
    ] {
        assert_eq!(named(source), LIB, "{source}");
    }
    // The importing module names `__all__` too, so its own `__all__` is unread (`binders.rs`).
    let found = named("from app.lib import __all__ as names\nnames.remove('f')\n");
    assert_eq!(found, ["app.lib", "app.writer"]);
}

#[test]
fn a_package_that_escapes_withholds_each_module_below_it() {
    let all = [
        "app",
        "app.dyn",
        "app.kinds",
        "app.lib",
        "app.other",
        "app.writer",
    ];
    assert_eq!(named("import app\ngetattr(app, 'lib').f = 1\n"), all);
}

#[test]
fn an_imported_name_of_unknown_kind_escapes_its_module_only_when_it_may_be_a_module() {
    assert_eq!(named("from app.dyn import DYN\nDYN.run = 1\n"), ["app.dyn"]);
    assert_eq!(named("from app.dyn import DYN\nuse(DYN)\n"), ["app.dyn"]);
    // A function or a class is no module: a call or a write to its attribute changes no namespace.
    assert!(named("from app.lib import f\nf()\nf.run = 1\nuse(f)\n").is_empty());
}

/// AD-530: an imported name whose origin cannot be a module of the scan escapes nothing: a
/// constant, a display, a call of a builtin type, a copy of such a name, an import that leaves the
/// scan. A name with two binders, or with a call of any other function, stays unknown.
#[test]
fn an_imported_name_of_inert_origin_escapes_nothing() {
    for name in [
        "NUMBER", "TEXT", "PAIR", "TUPLE", "COPY", "CHAIN", "MOD", "TYPES", "KEYS",
    ] {
        let source = format!("from app.kinds import {name}\nuse({name})\n{name}.run = 1\n");
        assert!(named(&source).is_empty(), "{name}");
    }
    // Two binders, an attribute of a module and a container of a call result: each stays unknown,
    // because an element of the value can be a module of the scan. A container that names a
    // module of the scan escapes that module in its own module already.
    for name in ["TWICE", "EXT", "LISTED"] {
        let source = format!("from app.kinds import {name}\nuse({name})\n");
        assert_eq!(named(&source), ["app.kinds"], "{name}");
    }
}

#[test]
fn a_binder_of_a_builtin_name_keeps_the_call_unknown() {
    let rebound = "tuple = make\nT = tuple(1)\ndef make(x): pass\n";
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/shadow.py", rebound),
        ("src/app/user.py", "from app.shadow import T\nuse(T)\n"),
    ]);
    assert!(found.opaque_surface.contains("app.shadow"));
}

#[test]
fn a_direct_attribute_load_and_a_call_of_it_are_harmless() {
    for source in [
        "from app import lib\nvalue = lib.f\nlib.f()\nprint(lib.f.__name__)\n",
        "import app.lib\napp.lib.f()\nx = app.lib.f\n",
        "class C:\n    def go(self):\n        self.x = 1\n",
        "def go(item):\n    item.x = 1\n",
        "import os\nos.environ['A'] = '1'\n",
    ] {
        assert!(named(source).is_empty(), "{source}");
    }
}
