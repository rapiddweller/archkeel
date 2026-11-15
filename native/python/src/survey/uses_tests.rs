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
    let all = ["app", "app.lib", "app.other", "app.writer"];
    assert_eq!(named("import app\ngetattr(app, 'lib').f = 1\n"), all);
}

#[test]
fn an_imported_name_of_unknown_kind_escapes_its_module_only_when_it_may_be_a_module() {
    assert_eq!(
        named("from app.other import VALUE\nVALUE.run = 1\n"),
        ["app.other"]
    );
    assert_eq!(
        named("from app.other import VALUE\nuse(VALUE)\n"),
        ["app.other"]
    );
    // A function or a class is no module: a call or a write to its attribute changes no namespace.
    assert!(named("from app.lib import f\nf()\nf.run = 1\nuse(f)\n").is_empty());
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
        ("src/app/lib.py", "VALUE = 1\ncode = 2\nprint(code)\n"),
        (
            "src/app/writer.py",
            "from app.lib import VALUE\nuse(VALUE)\n",
        ),
    ]);
    assert!(!found.opaque_surface.contains("app.lib"));
    assert!(!found.unknowns.is_empty());
}
