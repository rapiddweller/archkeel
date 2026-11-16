// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a `setattr` or `delattr` on a copied local writes no module of the scan (AD-530,
// decision 5, `copy_local.rs`); each other first argument keeps the escape.

use crate::survey::targets::tests::surveyed;

/// AD-530, decision 5: a `setattr` or `delattr` on a local whose one binding is `copy.copy` or
/// `copy.deepcopy` of one argument is no write to a module of the scan (`copy_local.rs`). Any other
/// first argument keeps the escape: a parameter, an attribute or a subscript of a local, a local
/// with another binding or a second binding, and a copier that is not the one import of `copy`.
#[test]
fn a_setattr_on_a_copied_local_keeps_the_names_of_its_module_inert() {
    let copied = "from copy import copy\ndef f(): pass\ndef g(x):\n    v = copy(x)\n";
    for (source, escaped) in [
        (format!("{copied}    setattr(v, 'a', 1)\n"), false),
        (format!("{copied}    delattr(v, 'a')\n"), false),
        (
            "import copy\ndef f(): pass\ndef g(x):\n    v = copy.deepcopy(x)\n    setattr(v, 'a', 1)\n".to_owned(),
            false,
        ),
        (
            "from copy import deepcopy as dc\ndef f(): pass\ndef g(x):\n    v = dc(x)\n    setattr(v, 'a', 1)\n".to_owned(),
            false,
        ),
        // A parameter, an attribute or a subscript of a copy: a copy keeps the attributes.
        ("def f(): pass\ndef g(obj, v):\n    setattr(obj, 'a', v)\n".to_owned(), true),
        (format!("{copied}    setattr(v.inner, 'a', 1)\n"), true),
        (format!("{copied}    setattr(v['k'], 'a', 1)\n"), true),
        // The memo of `deepcopy` can give any object.
        (
            "from copy import deepcopy\ndef f(): pass\ndef g(x, memo):\n    v = deepcopy(x, memo)\n    setattr(v, 'a', 1)\n".to_owned(),
            true,
        ),
        // A second binding, a local copier, a copier of another module, a conditional import.
        (format!("{copied}    v = x\n    setattr(v, 'a', 1)\n"), true),
        (format!("{copied}    def h():\n        nonlocal v\n    setattr(v, 'a', 1)\n"), true),
        (
            "def f(): pass\ndef g(copy, x):\n    v = copy(x)\n    setattr(v, 'a', 1)\n".to_owned(),
            true,
        ),
        (
            "from app.helpers import copy\ndef f(): pass\ndef g(x):\n    v = copy(x)\n    setattr(v, 'a', 1)\n".to_owned(),
            true,
        ),
        (
            "try:\n    from copy import copy\nexcept ImportError:\n    copy = None\ndef f(): pass\ndef g(x):\n    v = copy(x)\n    setattr(v, 'a', 1)\n".to_owned(),
            true,
        ),
        // A copy of the enclosing function, or at module scope, is no copied local of this scope.
        (format!("{copied}    def h():\n        setattr(v, 'a', 1)\n"), true),
        ("from copy import copy\ndef f(): pass\nv = copy(f)\nsetattr(v, 'a', 1)\n".to_owned(), true),
        ("def f(): pass\ndef g():\n    setattr(make(), 'f', 1)\n".to_owned(), true),
        ("def f(): pass\nsetattr(module, 'f', other)\n".to_owned(), true),
        (
            "def f(): pass\nimport sys\ndef g():\n    setattr(sys.modules[__name__], 'f', 1)\n".to_owned(),
            true,
        ),
    ] {
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/lib.py", &source),
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

/// A word of a copy hook in any module of the scan, or a module `copy` of the scan, withholds the
/// proof of a copied local (`copy_local.rs`, fact 3).
#[test]
fn a_copy_hook_anywhere_in_the_scan_withholds_the_copied_local() {
    let lib = "from copy import copy\ndef f(): pass\ndef g(x):\n    v = copy(x)\n    setattr(v, 'a', 1)\n";
    for (path, text, escaped) in [
        ("src/app/other.py", "VALUE = 1\n", false),
        (
            "src/app/other.py",
            "class K:\n    def __copy__(self):\n        return self\n",
            true,
        ),
        (
            "src/app/other.py",
            "class K:\n    def __reduce_ex__(self, p):\n        return p\n",
            true,
        ),
        (
            "src/app/other.py",
            "class K:\n    def __new__(cls):\n        return cls\n",
            true,
        ),
        ("src/app/other.py", "import copyreg\n", true),
        (
            "src/app/other.py",
            "def put(k, f):\n    setattr(k, '__deepcopy__', f)\n",
            true,
        ),
        ("src/app/other.py", "import sys\nsys.settrace(None)\n", true),
        (
            "src/app/other.py",
            "def f(frame):\n    frame.f_locals['v'] = 1\n",
            true,
        ),
    ] {
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/lib.py", lib),
            (path, text),
            (
                "src/app/writer.py",
                "from app.lib import f\nuse(f)\nf.run = 1\n",
            ),
        ]);
        assert_eq!(found.opaque_surface.contains("app.lib"), escaped, "{text}");
    }
}
