// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `Annotated[X, Field(...)]` makes an alias object, not a module (AD-552), unless the
// scan can replace the factory. AD-568 names the statements that can: Python 3.12 changes
// `typing.Annotated` by each of the forms below, and by none of the quiet forms.

use crate::survey::targets::tests::surveyed;

/// True when the typing alias of `app.lib` stays withheld with `patch` in the scan.
fn withheld(patch: &str) -> bool {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        (
            "src/app/lib.py",
            "from typing import Annotated\nVALUE = Annotated[int, meta()]\n",
        ),
        ("src/app/patch.py", patch),
        (
            "src/app/writer.py",
            "from app.lib import VALUE\nuse(VALUE)\n",
        ),
    ]);
    found.opaque_surface.contains("app.lib")
}

#[test]
fn a_store_or_delete_of_a_factory_or_class_attribute_withholds_the_alias() {
    for patch in [
        "import typing\ntyping.Annotated = other\n",
        "import typing as t\nt.Optional = other\n",
        "import typing\ndel typing.Union\n",
        "def go(m):\n    m.Annotated = other\n",
        "def go(k):\n    k.__getitem__ = other\n",
        "def go(k):\n    k.__class_getitem__ = other\n",
        "def go(k):\n    k.__call__ = other\n",
        "def go(m):\n    m.__dict__ = {}\n",
        "def go(m):\n    m.__class__ = other\n",
        "def go(k):\n    k.__new__ = other\n",
    ] {
        assert!(withheld(patch), "{patch}");
    }
}

#[test]
fn a_set_or_delete_call_withholds_the_alias_unless_it_names_an_unrelated_attribute() {
    for patch in [
        "import typing\nsetattr(typing, 'Annotated', other)\n",
        "import typing\ndelattr(typing, 'Annotated')\n",
        "import typing\ntyping.__setattr__('Annotated', other)\n",
        "import typing\ntyping.__delattr__('Annotated')\n",
        "import typing\nobject.__setattr__(typing, name, other)\n",
        "import typing\nobject.__setattr__(typing, 'Annotated', other)\n",
        "import typing\ntype.__setattr__(typing, 'Annotated', other)\n",
        "import typing\nobject.__delattr__(typing, 'Annotated')\n",
    ] {
        assert!(withheld(patch), "{patch}");
    }
    // A literal name that is no factory name changes no factory of `typing`.
    assert!(!withheld(
        "def go(s):\n    object.__setattr__(s, 'root', 1)\n"
    ));
}

#[test]
fn a_write_through_a_namespace_mapping_withholds_the_alias() {
    for patch in [
        "import typing\nvars(typing)['Annotated'] = other\n",
        "import typing\ntyping.__dict__['Annotated'] = other\n",
        "import typing\ntyping.__dict__.update(Annotated=other)\n",
        "import typing\ntyping.__dict__.setdefault('Annotated', other)\n",
        "import typing\ntyping.__dict__.pop('Annotated')\n",
        "import typing\ndel typing.__dict__['Annotated']\n",
        "import typing\nvars(typing).update(Annotated=other)\n",
        "import typing\nspace = typing.__dict__\nspace['Annotated'] = other\n",
        "import typing\nspace = vars(typing)\n",
        "import typing\nkeep(typing.__dict__)\n",
    ] {
        assert!(withheld(patch), "{patch}");
    }
    for read in [
        "def go(x):\n    return Cls(**x.__dict__)\n",
        "def go(x):\n    return x.__dict__.keys() != {1}\n",
        "def go(x):\n    for key in x.__dict__:\n        use(key)\n",
        "def go(x):\n    return x.__dict__['a'] + len(vars(x)) + x.__dict__.get('b', 0)\n",
    ] {
        assert!(!withheld(read), "{read}");
    }
}

#[test]
fn a_write_into_sys_modules_withholds_the_alias_unless_the_key_is_another_literal() {
    for patch in [
        "import sys\nsys.modules['typing'] = other\n",
        "import sys\nsys.modules['typing_extensions'] = other\n",
        "import sys\nsys.modules[name] = other\n",
        "import sys\ndel sys.modules['typing']\n",
        "import sys\nsys.modules.update(table)\n",
        "import sys\nsys.modules.pop('typing')\n",
        "from sys import modules\nmodules['typing'] = other\n",
    ] {
        assert!(withheld(patch), "{patch}");
    }
    assert!(!withheld("import sys\nsys.modules['cx_Oracle'] = other\n"));
}

#[test]
fn an_alias_stays_proven_when_the_scan_only_stores_other_names() {
    for patch in [
        "class C:\n    def go(self):\n        self.x = 1\n        self.Name = 2\n",
        "def go(item):\n    item.x = 1\n",
    ] {
        assert!(!withheld(patch), "{patch}");
    }
}
