// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a route through a module is proven only for the namespace that the module builds
// (AD-504). A write to a module of the scan from another module names it in the survey; a write to
// anything else names nothing.

use crate::survey::targets::tests::surveyed;

/// The modules that the survey cannot prove a route through, for a writer module.
fn named(writer: &str) -> Vec<String> {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/lib.py", "def f(): pass\n__all__ = ['f']\n"),
        ("src/app/other.py", "VALUE = 1\n"),
        ("src/app/writer.py", writer),
    ]);
    let mut names: Vec<String> = found.opaque_surface.into_iter().collect();
    names.sort();
    names
}

#[test]
fn each_write_to_a_module_of_the_scan_names_it() {
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
        "lib.__all__.append('g')\n",
        "lib.__all__[0] = 'g'\n",
        "lib.__dict__['f'] = 1\n",
        "lib.__dict__.update({'f': 1})\n",
        "vars(lib)['f'] = 1\n",
        "(lib.f, other) = (1, 2)\n",
    ] {
        assert_eq!(named(&format!("{prefix}{write}")), ["app.lib"], "{write}");
    }
}

#[test]
fn a_write_through_each_import_form_names_the_module() {
    for source in [
        "import app.lib\napp.lib.f = 1\n",
        "import app.lib as lib\nlib.f = 1\n",
        "import app.lib as lib\nlib.f = 1\n",
        "from app import lib as moved\nmoved.f = 1\n",
        "def go():\n    from app import lib\n    lib.f = 1\n",
        "import importlib\nimportlib.import_module('app.lib').f = 1\n",
        "__import__('app.lib').f = 1\n",
    ] {
        assert_eq!(named(source), ["app.lib"], "{source}");
    }
}

#[test]
fn an_imported_name_of_unknown_kind_names_the_module_it_comes_from() {
    assert_eq!(named("from app.lib import f\nf.run = 1\n"), ["app.lib"]);
}

#[test]
fn a_write_to_anything_else_names_nothing() {
    for source in [
        "class C:\n    def go(self):\n        self.x = 1\n",
        "def go(item):\n    item.x = 1\n",
        "from app import lib\nvalue = lib.f\nprint(lib.__all__)\n",
        "import os\nos.environ['A'] = '1'\n",
    ] {
        assert!(named(source).is_empty(), "{source}");
    }
}
