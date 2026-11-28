// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The class of the names that an `eval` or `exec` call hands on (#2239). One call in one module.

use archkeel_facts::vocab::SiteNamespace;
use archkeel_facts::GapFact;

use crate::survey::targets::tests::surveyed;

/// The classes of the `eval` and `exec` sites of `app.calc`, in the order of the gaps.
fn classes(source: &str) -> Vec<Option<SiteNamespace>> {
    let files = [("src/app/__init__.py", ""), ("src/app/calc.py", source)];
    let found = surveyed(&files);
    found
        .unknowns
        .iter()
        .filter_map(|gap| match &gap.data {
            GapFact::SourceResolutionGap(data) => {
                data.trojan_horse.as_ref().map(|site| (data, site))
            }
            _ => None,
        })
        .filter(|(data, _)| {
            data.module
                .as_ref()
                .is_some_and(|m| m.as_str() == "app.calc")
        })
        .map(|(data, _)| data.namespace)
        .collect()
}

/// The class of the one `eval` or `exec` site; `None` when no site states one.
fn one(source: &str) -> Option<SiteNamespace> {
    let found: Vec<SiteNamespace> = classes(source).into_iter().flatten().collect();
    assert!(found.len() <= 1, "{source}: {found:?}");
    found.first().copied()
}

#[test]
fn a_new_mapping_is_fresh() {
    for source in [
        "def f(text):\n    return eval(text, {})\n",
        "def f(text):\n    exec(text, {'a': 1}, {})\n",
        "def f(text):\n    return eval(text, dict(a=1))\n",
        "def f(text, ns):\n    return eval(text, globals=dict(ns))\n",
    ] {
        assert_eq!(one(source), Some(SiteNamespace::Fresh), "{source}");
    }
}

#[test]
fn the_names_of_the_product_are_shared() {
    for source in [
        "def f(text):\n    return eval(text, globals())\n",
        "def f(text):\n    exec(text, vars())\n",
        "def f(text):\n    exec(text, locals())\n",
        "def f(text):\n    return eval(text, __import__('app').__dict__)\n",
        "import sys\n\ndef f(text):\n    exec(text, sys.modules['app.calc'].__dict__)\n",
        "import sys\n\ndef f(text):\n    exec(text, sys.modules['app.calc'])\n",
    ] {
        assert_eq!(one(source), Some(SiteNamespace::Shared), "{source}");
    }
}

#[test]
fn no_mapping_runs_in_the_names_of_the_caller() {
    for source in [
        "def f(text):\n    return eval(text)\n",
        "def f(text):\n    exec(text)\n",
        "def f(text):\n    exec(text, None)\n",
    ] {
        assert_eq!(one(source), Some(SiteNamespace::Default), "{source}");
    }
}

#[test]
fn a_mapping_of_unknown_origin_is_unknown_and_a_spread_hides_the_arguments() {
    for source in [
        "def f(text, ns):\n    return eval(text, ns)\n",
        "def f(text, args):\n    return eval(*args)\n",
        "def f(text, kw):\n    return eval(text, **kw)\n",
        // A spread before the mapping moves every position (the globals can be shared).
        "def f(args):\n    exec(*args, {})\n",
        // `dict` is a parameter, a method or an import: not proved to build a new mapping.
        "def f(text, dict):\n    exec(text, dict())\n",
        "def f(text, box):\n    exec(text, box.dict())\n",
        "from app.other import dict\n\ndef f(text):\n    exec(text, dict())\n",
    ] {
        assert_eq!(one(source), Some(SiteNamespace::Unknown), "{source}");
    }
}

#[test]
fn compile_and_other_sites_state_no_class() {
    assert_eq!(
        one("def f(text):\n    return compile(text, 'x', 'exec')\n"),
        None
    );
    assert_eq!(one("import pickle\n"), None);
}
