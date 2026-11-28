// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A reserved name that an exact `str` tests is data (AD-1340, #2196).
//! `tests/test_collector_false_pass_python_reserved_text.py` runs the forms under CPython.

use super::super::split;
use super::*;

/// The details of the sites of the modules `app.m0`, `app.m1`, ...: (module index, detail).
fn sites(sources: &[&str]) -> Vec<(usize, String)> {
    let modules: Vec<Module> = sources
        .iter()
        .enumerate()
        .map(|(at, source)| {
            let tree = crate::test_tree(source, 14).expect("valid probe");
            let name = (format!("app/m{at}.py"), format!("app.m{at}"));
            Module::new(name.0, name.1, (*source).to_owned(), tree)
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

const HOOK: &str = "class K:\n    def __eq__(self, other):\n        return other\n\n    def __hash__(self):\n        return 1\n";

#[test]
fn a_reserved_name_that_an_exact_str_tests_is_no_site() {
    for source in [
        "def f(name):\n    return type(name) is str and name in {\"__globals__\", \"__builtins__\", \"__import__\"}\n",
        "def f(n):\n    return type(n) is str and n in (\"__globals__\", \"__import__\")\n",
        "def f(n):\n    return type(n) is str and n not in [\"__globals__\", \"f_code\"]\n",
        "def f(n):\n    return type(n) is str and n in frozenset({\"__globals__\"})\n",
        "def f(n):\n    return type(n) is str and n in \"__globals__\"\n",
        "def f(n):\n    return type(n) is str and n == \"__import__\"\n",
        "def f(n):\n    return type(n) is str and n != \"__builtins__\"\n",
        "def f(n, m):\n    return m and type(n) is str and n in {\"__code__\"} and m\n",
        "_R = frozenset({\"__globals__\", \"__import__\"})\n\n\ndef f(n):\n    return type(n) is str and n in _R\n",
        "_R = (\"__globals__\",)\n\n\ndef f(n):\n    return type(n) is str and n not in _R\n",
        "_R: frozenset = frozenset((\"__globals__\",))\n\n\ndef f(n):\n    return type(n) is str and n in _R\n",
    ] {
        assert_eq!(one(source), Vec::<String>::new(), "{source}");
        // The hooks of the scan do not matter: the left operand is an exact `str`.
        assert!(sites(&[source, HOOK]).iter().all(|(at, _)| *at != 0), "{source}");
    }
}

#[test]
fn every_other_test_of_a_reserved_name_keeps_the_site() {
    for source in [
        // No proof of the type of the other operand: its `__eq__` can run with the literal.
        "def f(n):\n    return n in {\"__globals__\"}\n",
        "def f(n):\n    return n in (\"__globals__\",)\n",
        "def f(n):\n    return n == \"__import__\"\n",
        "def f(n):\n    return \"__import__\" == n\n",
        "def f(a, b):\n    return a == \"__import__\" == b\n",
        "_R = frozenset({\"__globals__\"})\n\n\ndef f(n):\n    return n in _R\n",
        // The proof is `type(name) is str` right before the test of the same name.
        "def f(n):\n    return isinstance(n, str) and n in {\"__globals__\"}\n",
        "def f(n):\n    return type(n) == str and n in {\"__globals__\"}\n",
        "def f(n):\n    return type(n) is str or n in {\"__globals__\"}\n",
        "def f(n):\n    return n in {\"__globals__\"} and type(n) is str\n",
        "def f(n, m):\n    return type(n) is str and m in {\"__globals__\"}\n",
        "def f(n, m):\n    return type(n) is str and m and n in {\"__globals__\"}\n",
        "def f(n):\n    return type(n) is str and (n := other()) and n == \"__globals__\"\n",
        "def f(n):\n    return type(n) is str and (n, 1) == (\"__globals__\", 1)\n",
        "def f(n):\n    return type(n) is str and \"_\" in n == \"__globals__\"\n",
        "def f(n):\n    return type(n) is str and \"__globals__\" in n\n",
        // The display holds more than string literals: its construction can run user code.
        "def f(n):\n    return type(n) is str and n in {\"__globals__\", other()}\n",
        "def f(n):\n    return type(n) is str and n in {\"__globals__\", n}\n",
        "def f(n):\n    return type(n) is str and n in {\"__globals__\": 1}\n",
        // The names of a module or a class body can be read through a mapping of user code.
        "n = \"x\"\nok = type(n) is str and n in {\"__globals__\"}\n",
        "class C:\n    n = \"x\"\n    ok = type(n) is str and n in {\"__globals__\"}\n",
        "def f(n):\n    class C:\n        ok = type(n) is str and n == \"__globals__\"\n",
        "def f(n=(type(1) is str and n in {\"__globals__\"})):\n    return n\n",
        "def f(n):\n    return n\n\n\nclass C:\n    @(lambda g: g)\n    def m(self, k=type(n) is str and n in {\"__globals__\"}):\n        return k\n",
        // Any other place.
        "getattr(obj, \"__globals__\")\n",
        "hasattr(obj, \"__import__\")\n",
        "name = \"__import__\"\nf(name)\n",
        "x = \"__import__\"\n",
        "f(\"__import__\")\n",
        "d = {}\nd[\"__builtins__\"]\n",
        "def f():\n    return \"__import__\"\n",
        "__import__(name)\n",
        "def f(n):\n    match n:\n        case \"__import__\":\n            return 1\n",
    ] {
        assert!(!one(source).is_empty(), "{source}");
    }
}

#[test]
fn a_bound_display_is_data_only_when_each_use_is_a_guarded_test() {
    for source in [
        "_R = {\"__import__\"}\nfor n in _R:\n    getattr(o, n)\n",
        "_R = (\"__import__\",)\nx = _R[0]\n",
        "_R = {\"__import__\"}\n\n\ndef f(n):\n    return type(n) is str and n in _R or g(_R)\n",
        "_R = {\"__import__\"}\n_R.add(\"x\")\n",
        "_R = {\"__import__\"}\nS = _R\n",
        "_R = {\"__import__\"}\n_R = other\n",
        "_R = {\"__import__\"}\n_R |= {\"x\"}\n",
        "_R = {\"__import__\"}\nlist(_R)\n",
        "_R = {\"__import__\", name}\n",
        "_R = {\"__import__\"}\n\n\ndef f(_R):\n    return _R\n",
        // A name of a class body or a function, or a dunder: Python reads some of them by itself.
        "class C:\n    __match_args__ = (\"__globals__\",)\n\n\ndef f(n):\n    return type(n) is str and n in C.__match_args__\n",
        "class C:\n    _R = (\"__globals__\",)\n\n    def f(self, n):\n        return type(n) is str and n in _R\n",
        "def g():\n    _R = {\"__import__\"}\n\n    def f(n):\n        return type(n) is str and n in _R\n    return f\n",
        "__all__ = (\"__globals__\",)\n\n\ndef f(n):\n    return type(n) is str and n in __all__\n",
        "_R = {\"__import__\"}\n\n\ndef f(n):\n    return n in _R\n",
        "from external import *\n_R = {\"__import__\"}\n\n\ndef f(n):\n    return type(n) is str and n in _R\n",
    ] {
        assert!(!one(source).is_empty(), "{source}");
    }
}

#[test]
fn a_bound_display_that_another_module_reads_keeps_the_site() {
    let rules =
        "_R = frozenset({\"__import__\"})\n\n\ndef f(n):\n    return type(n) is str and n in _R\n";
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
fn a_scan_that_names_a_trace_function_or_a_frame_write_has_no_guard() {
    let guarded = "def f(n):\n    return type(n) is str and n in {\"__globals__\"}\n";
    assert_eq!(sites(&[guarded]), Vec::new());
    for hook in [
        "import sys\nsys.settrace(lambda *a: None)\n",
        "import sys\nsys.setprofile(None)\n",
        "import threading\nthreading.settrace(None)\n",
        "import threading\nthreading.setprofile(None)\n",
        "def trace(frame, event, arg):\n    frame.f_locals['n'] = 1\n",
        "def arm(frame):\n    frame.f_trace = None\n",
    ] {
        let found = sites(&[guarded, hook]);
        assert!(found.iter().any(|(at, _)| *at == 0), "{hook}: {found:?}");
    }
    // A scan that names none of them keeps the guard.
    assert!(!sites(&[guarded, "import sys\nsys.exit(0)\n"])
        .iter()
        .any(|(at, _)| *at == 0));
}
