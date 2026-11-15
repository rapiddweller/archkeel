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
        ("src/app/other.py", "VALUE = factory()\n"),
        ("src/app/const.py", "VALUE = 1\n"),
        ("src/app/dyn.py", "DYN = build()\ndef build(): pass\n"),
        (
            "src/app/kinds.py",
            "import json\nfrom os import path as P\nfrom app.const import VALUE as V\n\
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
        "app.const",
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
        "NUMBER", "TEXT", "PAIR", "TUPLE", "COPY", "CHAIN", "MOD", "TYPES", "KEYS", "LISTED",
    ] {
        let source = format!("from app.kinds import {name}\nuse({name})\n{name}.run = 1\n");
        assert!(named(&source).is_empty(), "{name}");
    }
    // Two binders and an attribute of a module stay unknown. A display is inert (a container that
    // names a module of the scan escapes that module in its own module already).
    for name in ["TWICE", "EXT"] {
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

#[test]
fn literal_bindings_do_not_escape_their_module() {
    for value in [
        "1", "'text'", "b'bytes'", "None", "True", "(1, 2)", "[1]", "{1: 2}", "{1}", "f'text'",
    ] {
        let source = format!("VALUE = {value}\n");
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/lib.py", &source),
            (
                "src/app/writer.py",
                "from app.lib import VALUE\nuse(VALUE)\n",
            ),
        ]);
        assert!(!found.opaque_surface.contains("app.lib"), "{value}");
    }
}

#[test]
fn uncertain_bindings_keep_the_escape() {
    for source in [
        "VALUE = 1\nVALUE = 2\n",
        "if flag:\n    VALUE = 1\n",
        "VALUE = 1\ndel VALUE\n",
        "VALUE = 1\nVALUE += 1\n",
        "VALUE = 1\nfrom external import *\n",
        "VALUE = 1\ndef __getattr__(name): pass\n",
        "VALUE = 1\nglobals()['VALUE'] = other\n",
        "VALUE = 1\nsetattr(module, 'VALUE', other)\n",
        "VALUE = 1\nimport sys\nsys.modules[__name__].VALUE = other\n",
        "VALUE = factory()\n",
    ] {
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/lib.py", source),
            (
                "src/app/writer.py",
                "from app.lib import VALUE\nuse(VALUE)\n",
            ),
        ]);
        assert!(found.opaque_surface.contains("app.lib"), "{source}");
    }
}

#[test]
fn reimports_follow_the_final_value_but_not_a_module() {
    for (origin, escaped) in [
        ("VALUE = 1\n", false),
        ("import app.other as VALUE\n", true),
    ] {
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/other.py", ""),
            ("src/app/origin.py", origin),
            ("src/app/mid.py", "from app.origin import VALUE\n"),
            ("src/app/lib.py", "from app.mid import VALUE\n"),
            (
                "src/app/writer.py",
                "from app.lib import VALUE\nuse(VALUE)\n",
            ),
        ]);
        assert_eq!(
            found.opaque_surface.contains("app.lib"),
            escaped,
            "{origin}"
        );
    }
}

#[test]
fn a_package_name_that_is_also_a_submodule_stays_escaped() {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/lib/__init__.py", "VALUE = 1\n"),
        ("src/app/lib/VALUE.py", ""),
        (
            "src/app/writer.py",
            "import app.lib.VALUE\nfrom app.lib import VALUE\nuse(VALUE)\n",
        ),
    ]);
    assert!(found.opaque_surface.contains("app.lib"));
}

#[test]
fn a_type_statement_makes_a_type_alias_not_a_module() {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/lib.py", "type VALUE = int\n"),
        (
            "src/app/writer.py",
            "from app.lib import VALUE\nuse(VALUE)\n",
        ),
    ]);
    assert!(!found.opaque_surface.contains("app.lib"));
}

#[test]
fn builtin_generic_aliases_are_values_only_when_the_builtin_is_unbound() {
    for (source, escaped) in [
        ("VALUE = list[int]\n", false),
        (
            "from typing import TypeAlias\nVALUE: TypeAlias = dict[str, int]\n",
            false,
        ),
        ("list = factory()\nVALUE = list[int]\n", true),
        ("VALUE = custom[int]\n", true),
    ] {
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/lib.py", source),
            (
                "src/app/writer.py",
                "from app.lib import VALUE\nuse(VALUE)\n",
            ),
        ]);
        assert_eq!(
            found.opaque_surface.contains("app.lib"),
            escaped,
            "{source}"
        );
    }
}

#[test]
fn an_unrelated_named_hazard_does_not_change_a_literal_binding() {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        (
            "src/app/lib.py",
            "VALUE = 1\nimport pickle\npickle.loads(payload)\n",
        ),
        (
            "src/app/writer.py",
            "from app.lib import VALUE\nuse(VALUE)\n",
        ),
    ]);
    assert!(!found.opaque_surface.contains("app.lib"));
    assert!(!found.unknowns.is_empty());
}

#[test]
fn typing_factories_prove_values_only_when_their_bindings_are_unmodified() {
    for (origin, patch, escaped) in [
        (
            "from typing import Annotated\nVALUE = Annotated[int, 1]\n",
            "",
            false,
        ),
        (
            "from typing import TypeVar\nVALUE = TypeVar('VALUE')\n",
            "",
            false,
        ),
        (
            "from typing import Annotated\nVALUE = Annotated[int, 1]\n",
            "import typing\ntyping.Annotated = other\n",
            true,
        ),
        (
            "from typing import Annotated\nVALUE = Annotated[int, 1]\n",
            "from typing import Annotated\nchange(Annotated)\n",
            true,
        ),
        (
            "from typing import Annotated\nVALUE = Annotated[int, 1]\n",
            "from typing_extensions import Annotated\nchange(Annotated)\n",
            true,
        ),
        (
            "from typing import Annotated\nAnnotated = other\nVALUE = Annotated[int, 1]\n",
            "",
            true,
        ),
        (
            "from typing import TypeAlias\nVALUE: TypeAlias = other()\n",
            "",
            true,
        ),
        (
            "from typing import Annotated\nVALUE = Annotated[int, metadata()]\n",
            "",
            true,
        ),
    ] {
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/lib.py", origin),
            ("src/app/patch.py", patch),
            (
                "src/app/writer.py",
                "from app.lib import VALUE\nuse(VALUE)\n",
            ),
        ]);
        assert_eq!(
            found.opaque_surface.contains("app.lib"),
            escaped,
            "{origin} {patch}"
        );
    }
}

#[test]
fn a_typing_factory_that_escapes_through_a_reexport_is_not_trusted() {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/mid.py", "from typing import Annotated\n"),
        (
            "src/app/lib.py",
            "from app.mid import Annotated\nVALUE = Annotated[int, 1]\n",
        ),
        (
            "src/app/patch.py",
            "from app.mid import Annotated\nchange(Annotated)\n",
        ),
        (
            "src/app/writer.py",
            "from app.lib import VALUE\nuse(VALUE)\n",
        ),
    ]);
    assert!(found.opaque_surface.contains("app.lib"));
}

#[test]
fn writing_the_runtime_type_of_a_typing_alias_blocks_the_factory_proof() {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/lib.py", "from typing import Annotated\nVALUE = Annotated[int, 1]\n"),
        ("src/app/patch.py", "from typing import Annotated\nalias = Annotated[int, 1]\ncls = type(alias)\ncls.__new__ = replacement\n"),
        ("src/app/writer.py", "from app.lib import VALUE\nuse(VALUE)\n"),
    ]);
    assert!(found.opaque_surface.contains("app.lib"));
}

/// AD-530, decision 5: a `setattr` or `delattr` on a local name of a function, or on an attribute
/// of one, is no write to a module of the scan. Any other first argument keeps the escape.
#[test]
fn a_setattr_on_a_local_object_keeps_the_names_of_its_module_inert() {
    for (source, escaped) in [
        (
            "def f(): pass\ndef g(obj, v):\n    setattr(obj, 'a', v)\n",
            false,
        ),
        (
            "def f(): pass\ndef g(obj):\n    delattr(obj.inner, 'a')\n",
            false,
        ),
        (
            "def f(): pass\ndef g():\n    o = make()\n    setattr(o['k'], 'a', 1)\n",
            false,
        ),
        ("def f(): pass\nsetattr(module, 'f', other)\n", true),
        (
            "def f(): pass\ndef g():\n    setattr(make(), 'f', 1)\n",
            true,
        ),
        (
            "def f(): pass\ndef g(obj):\n    global lib\n    setattr(lib, 'f', 1)\n",
            true,
        ),
        (
            "def f(): pass\nimport sys\ndef g():\n    setattr(sys.modules[__name__], 'f', 1)\n",
            true,
        ),
        (
            "def f(): pass\ndef g():\n    def h():\n        setattr(shared, 'f', 1)\n",
            true,
        ),
    ] {
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/lib.py", source),
            (
                "src/app/writer.py",
                "from app.lib import f\nuse(f)\nf.run = 1\n",
            ),
        ]);
        assert_eq!(
            found.opaque_surface.contains("app.lib"),
            escaped,
            "{source}"
        );
    }
}
