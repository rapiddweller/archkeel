// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A reserved name that is only tested is data (AD-1340, #2196). `tests/test_collector_false_pass_python_reserved_text.py`
//! runs the escaping forms under CPython.

use super::super::split;
use super::*;

/// The details of the sites of the modules `app.m0`, `app.m1`, ...: (module index, detail).
fn sites(sources: &[&str]) -> Vec<(usize, String)> {
    let modules: Vec<Module> = sources
        .iter()
        .enumerate()
        .map(|(at, source)| {
            let tree = crate::test_tree(source, 14).expect("valid probe");
            Module::new(
                format!("app/m{at}.py"),
                format!("app.m{at}"),
                (*source).to_owned(),
                tree,
            )
        })
        .collect();
    let binders: Vec<Binders> = modules.iter().map(|m| Binders::of(&m.tree)).collect();
    let (_, found) = split(&modules, &binders, (None, false), false);
    found
        .into_iter()
        .map(|(at, site)| (at, site.detail))
        .collect()
}

fn one(source: &str) -> Vec<String> {
    sites(&[source])
        .into_iter()
        .map(|(_, detail)| detail)
        .collect()
}

#[test]
fn a_reserved_name_that_is_only_tested_is_no_site() {
    for source in [
        "def f(name):\n    return type(name) is str and name in {\"__globals__\", \"__builtins__\", \"__import__\"}\n",
        "def f(n):\n    return n in (\"__globals__\", \"__import__\")\n",
        "def f(n):\n    return n not in [\"__globals__\", \"f_code\"]\n",
        "def f(n):\n    return n in frozenset({\"__globals__\"})\n",
        "def f(n):\n    return n in \"__globals__\"\n",
        "def f(n):\n    return n == \"__import__\"\n",
        "def f(n):\n    return n != \"__builtins__\"\n",
        "def f(n):\n    return \"import_module\" == n\n",
        "def f(a, b):\n    return a == \"__import__\" == b\n",
        "def f(n):\n    if n in {\"__import__\"} or n == \"__code__\":\n        return 1\n",
        "_R = frozenset({\"__globals__\", \"__import__\"})\n\n\ndef f(n):\n    return n in _R\n",
        "_R = (\"__globals__\",)\n\n\ndef f(n):\n    return n not in _R\n",
        "_R: frozenset = frozenset((\"__globals__\",))\n\n\ndef f(n):\n    return n in _R\n",
        "def f(n):\n    r = {\"__import__\"}\n    return n in r\n",
    ] {
        assert_eq!(one(source), Vec::<String>::new(), "{source}");
    }
}

#[test]
fn a_reserved_name_that_goes_anywhere_else_keeps_the_site() {
    for source in [
        "getattr(obj, \"__globals__\")\n",
        "hasattr(obj, \"__import__\")\n",
        "name = \"__import__\"\nf(name)\n",
        "x = \"__import__\"\n",
        "f(\"__import__\")\n",
        "d = {}\nd[\"__builtins__\"]\n",
        "d = {\"__import__\": 1}\n",
        "def f():\n    return \"__import__\"\n",
        "__import__(name)\n",
        "x = [\"__import__\"]\n",
        "def f(n):\n    if n in {\"__globals__\"}:\n        return getattr(n, \"__globals__\")\n",
        "def f(n):\n    return n in {\"__import__\": 1}\n",
        "def f(n):\n    return n in ((\"__import__\",),)\n",
        "def f(n):\n    return \"__import__\" in n\n",
        "def f(n):\n    match n:\n        case \"__import__\":\n            return 1\n",
    ] {
        assert!(!one(source).is_empty(), "{source}");
    }
}

#[test]
fn a_bound_display_is_data_only_when_each_use_is_an_in_test() {
    for source in [
        // The elements go on through an iteration, a subscript, a call, a method or a store.
        "_R = {\"__import__\"}\nfor n in _R:\n    getattr(o, n)\n",
        "_R = (\"__import__\",)\nx = _R[0]\n",
        "_R = {\"__import__\"}\n\n\ndef f(n):\n    return n in _R or g(_R)\n",
        "_R = {\"__import__\"}\n_R.add(\"x\")\n",
        "_R = {\"__import__\"}\nS = _R\n",
        "_R = {\"__import__\"}\n_R = other\n",
        "_R = {\"__import__\"}\n_R |= {\"x\"}\n",
        "_R = {\"__import__\"}\nlist(_R)\n",
        "_R = {\"__import__\", name}\n",
        "_R = {\"__import__\"}\n\n\ndef f(_R):\n    return _R\n",
        "from external import *\n_R = {\"__import__\"}\n\n\ndef f(n):\n    return n in _R\n",
        "_R = {\"__import__\"}\nglobals()[\"_R\"]\n",
    ] {
        assert!(!one(source).is_empty(), "{source}");
    }
}

#[test]
fn a_bound_display_that_another_module_reads_keeps_the_site() {
    let rules = "_R = frozenset({\"__import__\"})\n\n\ndef f(n):\n    return n in _R\n";
    for other in [
        "from app.m0 import _R\nfor n in _R:\n    getattr(o, n)\n",
        "import app.m0 as r\nfor n in r._R:\n    pass\n",
        "from app.m0 import *\n",
        "import app.m0\nvalue = getattr(app.m0, \"_R\")\n",
    ] {
        let found = sites(&[rules, other]);
        assert!(found.iter().any(|(at, _)| *at == 0), "{other}: {found:?}");
    }
    // Control: another module that reads another name leaves the display inert.
    let found = sites(&[rules, "from app.m0 import f\n"]);
    assert!(!found.iter().any(|(at, _)| *at == 0), "{found:?}");
}

#[test]
fn a_scan_that_defines_an_equality_hook_has_no_inert_text() {
    let test = "def f(n):\n    return n == \"__globals__\" or n in {\"__import__\"}\n";
    assert_eq!(sites(&[test]), Vec::new());
    for hook in [
        "class K:\n    def __eq__(self, other):\n        return other\n",
        "class K:\n    def __ne__(self, other):\n        return other\n",
        "class K:\n    __eq__ = lambda self, other: other\n",
        "K.__eq__ = lambda self, other: other\n",
        "type('K', (), {'__eq__': lambda self, other: other})\n",
        "setattr(K, '__ne__', lambda self, other: other)\n",
    ] {
        let found = sites(&[test, hook]);
        assert!(found.iter().any(|(at, _)| *at == 0), "{hook}: {found:?}");
    }
}

#[test]
fn a_set_test_needs_a_hash_beside_the_equality_hook() {
    let sets = "def f(n):\n    return n in {\"__globals__\"}\n";
    let seq = "def f(n):\n    return n in (\"__globals__\",)\n";
    let eq = "def f(n):\n    return n == \"__globals__\"\n";
    let eq_only = "class K:\n    def __eq__(self, other):\n        return other\n";
    // `__eq__` alone makes the class unhashable: a set test never reaches it.
    assert!(!sites(&[sets, eq_only]).iter().any(|(at, _)| *at == 0));
    for test in [seq, eq] {
        assert!(
            sites(&[test, eq_only]).iter().any(|(at, _)| *at == 0),
            "{test}"
        );
    }
    for hook in [
        "class K:\n    def __eq__(self, other):\n        return other\n\n    def __hash__(self):\n        return 1\n",
        "class K:\n    __hash__ = hash\n    __eq__ = lambda self, other: other\n",
        "K.__eq__ = lambda self, other: other\n",
        "type('K', (), {'__eq__': lambda self, other: other, '__hash__': hash})\n",
    ] {
        assert!(sites(&[sets, hook]).iter().any(|(at, _)| *at == 0), "{hook}");
    }
}

#[test]
fn an_exact_str_has_no_hook_that_runs_with_the_literal() {
    let hook = "class K:\n    def __eq__(self, other):\n        return other\n\n    def __hash__(self):\n        return 1\n";
    for guarded in [
        "def f(n):\n    return type(n) is str and n in {\"__globals__\", \"__import__\"}\n",
        "def f(n):\n    return type(n) == str and n in (\"__globals__\",)\n",
        "def f(n):\n    return type(n) is str and n == \"__import__\"\n",
        "def f(n, m):\n    return m and type(n) is str and n in [\"__code__\"]\n",
    ] {
        assert!(
            !sites(&[guarded, hook]).iter().any(|(at, _)| *at == 0),
            "{guarded}"
        );
    }
    // The proof is for the name on the left, in an `and` after it: nothing else.
    for open in [
        "def f(n):\n    return n in {\"__globals__\"}\n",
        "def f(n, m):\n    return type(n) is str and m in {\"__globals__\"}\n",
        "def f(n):\n    return type(n) is str or n in {\"__globals__\"}\n",
        "def f(n):\n    return n in {\"__globals__\"} and type(n) is str\n",
        "def f(n):\n    return isinstance(n, str) and n in {\"__globals__\"}\n",
        "def f(n):\n    return type(n) is str and (n, 1) == (\"__globals__\", 1)\n",
    ] {
        assert!(
            sites(&[open, hook]).iter().any(|(at, _)| *at == 0),
            "{open}"
        );
    }
}
