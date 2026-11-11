// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::parse::parse;

fn modules(files: &[(&str, &str, &str)]) -> Vec<Module> {
    files
        .iter()
        .map(|(rel, name, text)| {
            let tree = parse(text, 13).expect("valid source");
            Module::new(
                (*rel).to_owned(),
                (*name).to_owned(),
                (*text).to_owned(),
                tree,
            )
        })
        .collect()
}

/// One record as (source, target, symbol, binding, type checking, module level, reexport).
type Row = (String, String, Option<String>, String, bool, bool, bool);

fn rows(files: &[(&str, &str, &str)]) -> Vec<Row> {
    let modules = modules(files);
    let binders: Vec<Binders> = modules
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let mut evidence = EvidenceMap::new();
    let mut found: Vec<_> = collect(&modules, &binders, "app", &mut evidence)
        .into_iter()
        .map(|record| {
            let data = record.data.data().clone();
            (
                data.source_module.as_str().to_owned(),
                data.target_module.as_str().to_owned(),
                data.symbol,
                data.binding.unwrap_or_default(),
                data.under_type_checking,
                data.module_level_import,
                data.reexport,
            )
        })
        .collect();
    found.sort();
    found
}

fn row(
    source: &str,
    target: &str,
    symbol: Option<&str>,
    binding: &str,
    flags: (bool, bool, bool),
) -> Row {
    let (guarded, level, reexport) = flags;
    let symbol = symbol.map(str::to_owned);
    (
        source.into(),
        target.into(),
        symbol,
        binding.into(),
        guarded,
        level,
        reexport,
    )
}

#[test]
fn a_relative_import_resolves_as_importlib_does() {
    assert_eq!(resolve(1, "x", "a.b").as_deref(), Some("a.b.x"));
    assert_eq!(resolve(2, "", "a.b").as_deref(), Some("a"));
    assert_eq!(resolve(3, "", "a.b"), None);
    assert_eq!(resolve(1, "x", ""), None);
}

#[test]
fn a_from_import_names_a_local_submodule_unless_the_package_binds_the_name() {
    let files = [
        (
            "app/__init__.py",
            "app",
            "from . import sub\nfrom .sub import f as sub2\n",
        ),
        ("app/sub.py", "app.sub", "def f(): pass\n"),
        (
            "app/user.py",
            "app.user",
            "from app import sub, sub2\nfrom ...x import y\n",
        ),
    ];
    let unresolved = "<unresolved:...x:ImportError>";
    assert_eq!(
        rows(&files),
        [
            row("app", "app.sub", None, "sub", (false, true, true)),
            row("app", "app.sub", Some("f"), "sub2", (false, true, true)),
            row("app.user", unresolved, Some("y"), "y", (false, true, false)),
            row(
                "app.user",
                "app",
                Some("sub2"),
                "sub2",
                (false, true, false)
            ),
            row("app.user", "app.sub", None, "sub", (false, true, false)),
        ]
    );
}

#[test]
fn a_guarded_or_nested_import_keeps_its_place() {
    let text = "import typing\nif typing.TYPE_CHECKING:\n    import a.b\nelif x:\n    import c\n\
                else:\n    import d as e\ndef f():\n    from m import *\n";
    assert_eq!(
        rows(&[("app/m.py", "app.m", text)]),
        [
            row("app.m", "a.b", None, "a", (true, true, false)),
            row("app.m", "c", None, "c", (false, true, false)),
            row("app.m", "d", None, "e", (false, true, false)),
            row("app.m", "m", Some("*"), "*", (false, false, false)),
            row("app.m", "typing", None, "typing", (false, true, false)),
        ]
    );
}

#[test]
fn an_elif_type_checking_guards_only_its_own_body() {
    let text = "import typing\nif x:\n    import a\nelif typing.TYPE_CHECKING:\n    import b\n\
                else:\n    import c\n";
    assert_eq!(
        rows(&[("app/m.py", "app.m", text)]),
        [
            row("app.m", "a", None, "a", (false, true, false)),
            row("app.m", "b", None, "b", (true, true, false)),
            row("app.m", "c", None, "c", (false, true, false)),
            row("app.m", "typing", None, "typing", (false, true, false)),
        ]
    );
}

#[test]
fn a_literal_all_makes_a_unique_import_a_reexport() {
    let text = "from os import path, sep\n__all__ = ['path']\n";
    let found = rows(&[("app/m.py", "app.m", text)]);
    assert!(found[0].6, "path is in the one literal __all__");
    assert!(!found[1].6, "sep is not exported");
}
