// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a route through `app.lib` is withheld when a scanned module uses a name that `app.lib`
// binds and that may be a module (AD-504). The call of a bare class, of a builtin value type and
// arithmetic over numbers make no module (AD-560): Python 3.12 gives an instance, a `frozenset` or
// an `int` for each of them. Each form that Python can turn into another object keeps the escape.

use crate::survey::targets::tests::surveyed;

const TYPES: &str =
    "from dataclasses import dataclass\n\n@dataclass(frozen=True)\nclass K:\n    a: int = 0\n";

/// True when `app.lib` is withheld by the bare use of `VALUE` in a writer module.
fn escaped(lib: &str, extra: &[(&str, &str)]) -> bool {
    let mut files = vec![
        ("src/app/__init__.py", ""),
        ("src/app/types.py", TYPES),
        ("src/app/lib.py", lib),
        (
            "src/app/writer.py",
            "from app.lib import VALUE\nuse(VALUE)\n",
        ),
    ];
    files.extend_from_slice(extra);
    surveyed(&files).opaque_surface.contains("app.lib")
}

#[test]
fn a_call_that_makes_an_instance_of_a_bare_class_is_no_module() {
    for lib in [
        "class K:\n    pass\nVALUE = K()\n",
        "from dataclasses import dataclass\n@dataclass\nclass K:\n    a: int = 0\nVALUE = K()\n",
        "from app.types import K\nVALUE = K(a=1)\n",
        "from app import types\nfrom app.types import K as Q\nVALUE = Q()\n",
        "VALUE = frozenset({1, 2})\n",
        "VALUE = tuple([1, 2])\n",
        "VALUE = 100 * 1024 * 1024\n",
        "VALUE = -(2 + 3)\n",
    ] {
        assert!(!escaped(lib, &[]), "{lib}");
    }
}

#[test]
fn a_call_that_may_run_another_constructor_keeps_the_escape() {
    for lib in [
        // The call of a class can give any object: a base, a metaclass or `__new__` runs.
        "class K(Base):\n    pass\nVALUE = K()\n",
        "class K(metaclass=Meta):\n    pass\nVALUE = K()\n",
        "class K:\n    def __new__(cls):\n        return cls\nVALUE = K()\n",
        "class K:\n    __new__ = make\nVALUE = K()\n",
        // A decorator can return any object.
        "def deco(c):\n    return c\n@deco\nclass K:\n    pass\nVALUE = K()\n",
        "import dataclasses\n@dataclasses.dataclass\nclass K:\n    pass\nVALUE = K()\n",
        "from other import dataclass\n@dataclass\nclass K:\n    pass\nVALUE = K()\n",
        "def dataclass(c):\n    return c\n@dataclass\nclass K:\n    pass\nVALUE = K()\n",
        // A function can return a module.
        "def make():\n    return object()\nVALUE = make()\n",
        "from external import K\nVALUE = K()\n",
        // A rebound builtin is no builtin; a conditional class is no sole class.
        "frozenset = factory\nVALUE = frozenset({1})\n",
        "if flag:\n    class K:\n        pass\nVALUE = K()\n",
        "class K:\n    pass\nK = other\nVALUE = K()\n",
        "VALUE = 1 + other\n",
    ] {
        assert!(escaped(lib, &[]), "{lib}");
    }
}

#[test]
fn a_statement_that_patches_a_class_withholds_the_proof_of_each_instance() {
    let lib = "class K:\n    pass\nVALUE = K()\n";
    for patch in [
        "from app.lib import K\nK.__new__ = make\n",
        "from app.lib import K\nK.__class__ = Meta\n",
        "from app.lib import K\nsetattr(K, '__new__', make)\n",
        "from app.lib import K\ntype.__setattr__(K, '__new__', make)\n",
        "from app.lib import K\ndel K.__new__\n",
    ] {
        assert!(escaped(lib, &[("src/app/patch.py", patch)]), "{patch}");
    }
    // `object.__setattr__` raises on a class and a method name is no patch of it.
    let harmless = "class C:\n    def go(self):\n        object.__setattr__(self, 'x', 1)\n        self.y = 2\n        print(self.__class__)\n";
    assert!(!escaped(lib, &[("src/app/other_user.py", harmless)]));
}
