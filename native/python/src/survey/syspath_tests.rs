// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a write to `sys.path` is a gap of the whole run unless it provably adds no name that
// the scan imports (AD-528). The control is the form of K-python-realworld; each other form keeps
// the gap.

use crate::survey::targets::tests::{reasons, surveyed_in};

const WRITER: &str = "app/db/mig/env.py";
const K: &str = "import pathlib\nimport sys\n\nsys.path.append(str(pathlib.Path(__file__).resolve().parents[3]))\n";

/// The survey of `app/` with `writer` as `app/db/mig/env.py` and the extra files of the tree.
fn gap(writer: &str, extra: &[(&str, &str)]) -> bool {
    let mut files = vec![
        ("app/__init__.py", ""),
        ("app/db/__init__.py", ""),
        ("app/db/mig/__init__.py", ""),
        (WRITER, writer),
    ];
    files.extend_from_slice(extra);
    let found = surveyed_in(&files, &["app"], "app");
    reasons(&found)
        .iter()
        .any(|reason| reason.contains("import_system_change"))
}

#[test]
fn the_form_of_k_adds_no_imported_name_and_is_no_gap() {
    assert!(!gap(K, &[]));
    // A parent that is the same directory, counted with `.parent`.
    let parent = K.replace("parents[3]", "parent.parent.parent.parent");
    assert!(!gap(&parent, &[]));
    let named = "from pathlib import Path\nimport sys\n\nsys.path.append(str(Path(__file__).resolve().parents[3]))\n";
    assert!(!gap(named, &[]));
}

#[test]
fn the_other_write_forms_keep_the_gap() {
    for source in [
        // R1: insert at any index
        K.replace("append(", "insert(0, "),
        K.replace("append(", "insert(5, "),
        // R5: the expression
        K.replace(".resolve()", ""),
        K.replace("parents[3]", "parents[-1]"),
        K.replace("parents[3]", "parents[n]"),
        K.replace("parents[3]", "parents[4]"),
        K.replace("str(pathlib.Path(__file__).resolve().parents[3])", "pathlib.Path(__file__).resolve().parents[3]"),
        format!("__file__ = '/x/y.py'\n{K}"),
        format!("str = repr\n{K}"),
        format!("from os.path import *\n{K}"),
        K.replace("import sys\n", "import sys as other\n"),
        format!("import sys\n{K}"),
        // R5: not an expression statement of the module body
        format!("def go():\n    {}", K.lines().nth(3).unwrap_or_default()),
        format!("class C:\n    {}", K.lines().nth(3).unwrap_or_default()),
        "import pathlib\nimport sys\n\nif True:\n    sys.path.append(str(pathlib.Path(__file__).resolve().parents[3]))\n".to_owned(),
        // each other write
        "import sys\nsys.path.extend(['x'])\n".to_owned(),
        "import sys\nsys.path += ['x']\n".to_owned(),
    ] {
        assert!(gap(&source, &[]), "{source}");
    }
}

#[test]
fn a_name_that_the_scan_imports_and_the_directory_holds_keeps_the_gap() {
    let importer = (
        "app/db/use.py",
        "import colorsys\nimport docs\nimport x\nimport X2\n",
    );
    for entry in [
        ("colorsys.so", ""),
        ("docs.pyc", ""),
        ("docs/readme.md", ""),
        ("x.abi3.so", ""),
        ("X/m.py", ""),
        ("x.cpython-312-darwin.so", ""),
        ("x2.py", ""),
        ("x.pyd", ""),
        ("x.pyw", ""),
        ("x.cp312-win_amd64.pyd", ""),
    ] {
        assert!(gap(K, &[importer, entry]), "{entry:?}");
    }
    // A name that nothing imports is harmless.
    assert!(!gap(
        K,
        &[
            ("app/db/use.py", "import colorsys\n"),
            ("unused.py", ""),
            ("data/x.txt", "")
        ]
    ));
}

#[test]
fn a_literal_import_call_and_a_function_import_count() {
    let call = (
        "app/db/use.py",
        "import importlib\nm = importlib.import_module('docs.x')\n",
    );
    assert!(gap(K, &[call, ("docs/x.py", "")]));
    let inner = ("app/db/use.py", "def go():\n    import docs\n");
    assert!(gap(K, &[inner, ("docs/__init__.py", "")]));
}

#[test]
fn the_namespace_entry_is_exempt_only_as_the_scan_root_itself() {
    // CE3: `app.py` beside the package `app/`.
    assert!(gap(K, &[("app.py", "")]));
    // Another module-like entry of the same name beside the package.
    assert!(gap(K, &[("APP.py", "")]));
    // A relative import only: the namespace first segment is still in the set (CE1).
    let relative = "import pathlib\nimport sys\n\nsys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))\nfrom . import extra\n";
    let found = surveyed_in(
        &[
            ("src/app/__init__.py", ""),
            ("src/app/main.py", relative),
            ("src/app/extra.py", ""),
            ("app/extra.py", ""),
        ],
        &["src/app"],
        "app",
    );
    assert!(reasons(&found)
        .iter()
        .any(|reason| reason.contains("import_system_change")));
}

#[test]
fn two_writes_where_one_is_refused_keep_the_gap() {
    let two = format!("{K}import os\nsys.path.insert(0, os.getcwd())\n");
    assert!(gap(&two, &[]));
}
