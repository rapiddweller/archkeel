// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a read of `__globals__` is a dynamic import unless the dict is used only to look up a
// literal key (AD-530). A missed case is a false PASS, so each form that reaches `__builtins__` or
// leaves the survey has a case, and each inert neighbour too.

use crate::survey::targets::tests::{reasons, surveyed};

/// The gaps of the module `app.m` beside a second module `app.n`.
fn gaps(first: &str, second: &str) -> Vec<String> {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/m.py", first),
        ("src/app/n.py", second),
    ]);
    let mut all = reasons(&found);
    all.sort();
    all
}

fn clean(source: &str) -> bool {
    gaps(source, "").is_empty()
}

fn holds(source: &str) -> bool {
    gaps(source, "")
        .iter()
        .any(|reason| reason.contains("__globals__"))
}

#[test]
fn a_lookup_of_a_literal_key_reads_a_value_and_imports_nothing() {
    for source in [
        "def f(fn):\n    return getattr(fn, '__globals__', {}).get('__file__')\n",
        "def f(fn):\n    return fn.__globals__.get('__file__', None)\n",
        "def f(fn):\n    return fn.__globals__['__name__']\n",
        "def f(fn):\n    return '__file__' in fn.__globals__\n",
        "def f(fn):\n    g = fn.__globals__\n    return g.get('a'), g['b'], 'c' in g\n",
    ] {
        assert!(clean(source), "{source}");
    }
}

#[test]
fn a_dict_that_reaches_a_door_or_leaves_a_lookup_stays_a_gap() {
    for source in [
        "def f(fn):\n    return fn.__globals__\n",
        "def f(fn):\n    return fn.__globals__.get('__builtins__')\n",
        "def f(fn):\n    return fn.__globals__['__import__']\n",
        "def f(fn, key):\n    return fn.__globals__.get(key)\n",
        "def f(fn, key):\n    return fn.__globals__[key]\n",
        "def f(fn):\n    return fn.__globals__.items()\n",
        "def f(fn):\n    return fn.__globals__.copy()\n",
        "def f(fn):\n    fn.__globals__['x'] = 1\n",
        "def f(fn):\n    fn.__globals__.update(x=1)\n",
        "def f(fn):\n    return {**fn.__globals__}\n",
        "def f(fn):\n    return [k for k in fn.__globals__]\n",
        "def f(fn):\n    g = fn.__globals__\n    return g\n",
        "def f(fn):\n    g = fn.__globals__\n    g = {}\n    return g.get('x')\n",
        "def f(fn):\n    g = fn.__globals__\n    return lambda: g\n",
        "def f(fn):\n    g = fn.__globals__\n    h = g\n    return h.get('x')\n",
        "g = f.__globals__\n",
        "def f(fn):\n    g = fn.__globals__\n    return g.get('x') or g\n",
    ] {
        assert!(holds(source), "{source}");
    }
}

#[test]
fn a_dict_given_to_code_runner_or_an_unknown_callee_stays_a_gap() {
    for source in [
        "def f(fn):\n    g = fn.__globals__\n    return eval('1', g)\n",
        "def f(fn):\n    g = fn.__globals__\n    exec('x = 1', g)\n",
        "def f(fn, sink):\n    g = fn.__globals__\n    return sink.use(g)\n",
        "def f(fn):\n    g = fn.__globals__\n    return fn.helper(g)\n",
        "def f(fn):\n    g = fn.__globals__\n    return call(*[g])\n",
        "def f(fn):\n    g = fn.__globals__\n    return call(**{'x': g})\n",
        "def f(fn):\n    return list(fn.__globals__)\n",
        "def f(fn):\n    return dict(fn.__globals__)\n",
        "def f(fn):\n    return vars(fn.__globals__)\n",
    ] {
        assert!(holds(source), "{source}");
    }
}

#[test]
fn a_dict_given_to_a_call_outside_the_scan_is_inert() {
    for source in [
        "import typing\ndef f(fn):\n    g = fn.__globals__\n    return typing.get_type_hints(fn, g)\n",
        "from typing import get_type_hints\ndef f(fn):\n    g = fn.__globals__\n    return get_type_hints(fn, globalns=g)\n",
        "def f(fn):\n    return len(fn.__globals__)\n",
        "def f(fn):\n    return isinstance(fn.__globals__, dict)\n",
    ] {
        assert!(clean(source), "{source}");
    }
}

#[test]
fn a_dict_given_to_a_function_of_the_scan_follows_the_parameter() {
    let lookup = "def look(g, key):\n    return g.get('__file__')\n";
    let walk = "def walk(g):\n    return [k for k in g]\n";
    let relay = "def relay(g):\n    return look(g, 'x')\n";
    let call = "def f(fn):\n    g = fn.__globals__\n    return {callee}(g{rest})\n";
    let case = |defs: &str, callee: &str, rest: &str| {
        let tail = call.replace("{callee}", callee).replace("{rest}", rest);
        holds(&format!("{defs}{tail}"))
    };
    assert!(!case(lookup, "look", ", 'x'"));
    assert!(!case(&format!("{lookup}{relay}"), "relay", ""));
    assert!(case(walk, "walk", ""));
    // A parameter that the callee writes again is not the dict.
    assert!(case(
        "def put(g):\n    g = {}\n    return g.get('x')\n",
        "put",
        ""
    ));
    // A cycle, and a chain longer than the bound, are not inert.
    assert!(case(
        "def a(g):\n    return b(g)\ndef b(g):\n    return a(g)\n",
        "a",
        ""
    ));
    let chain: String = (0..6)
        .map(|n| format!("def c{n}(g):\n    return c{}(g)\n", n + 1))
        .chain(["def c6(g):\n    return g.get('x')\n".to_owned()])
        .collect();
    assert!(case(&chain, "c0", ""));
}

#[test]
fn a_function_of_another_module_is_followed_through_its_import() {
    let user = "from app.n import look\ndef f(fn):\n    g = fn.__globals__\n    return look(g)\n";
    assert!(gaps(user, "def look(g):\n    return g.get('__file__')\n").is_empty());
    assert!(!gaps(user, "def look(g):\n    return list(g)\n").is_empty());
    let relative = "from .n import look\ndef f(fn):\n    return look(fn.__globals__)\n";
    assert!(gaps(relative, "def look(g):\n    return g.get('x')\n").is_empty());
}

#[test]
fn a_local_name_with_the_name_of_a_door_is_no_door_but_the_module_is() {
    for source in [
        "def f(code):\n    return str(code)\n",
        "def f(eval):\n    return eval(1)\n",
        "def f():\n    exec = len\n    return exec('a')\n",
        "def f(types):\n    return types.FunctionType\n",
    ] {
        assert!(clean(source), "{source}");
    }
    for source in [
        "import code\ndef f(code=code):\n    return code\n",
        "def f(x):\n    y = [code for code in x]\n    return code.interact\n",
        "def f():\n    import code\n    return code.interact\n",
        "code = 1\ndef f():\n    return code\n",
        "def f():\n    def g(code):\n        return code\n    return code\n",
        "def f():\n    return code\n    code = 1\n",
    ] {
        let found = gaps(source, "");
        // Only an import binds the door module `code` (AD-539): a name that no import binds is no
        // loader, in a function or at module scope.
        let expected = source.contains("import code");
        assert_eq!(!found.is_empty(), expected, "{source}");
    }
}

#[test]
fn a_getattr_with_a_literal_attribute_reads_that_attribute_only() {
    for source in [
        "import types\nU = getattr(types, 'UnionType', None)\n",
        "import types\nU = getattr(types, 'GenericAlias')\n",
        "import json\nD = getattr(json, 'dumps', None)\n",
    ] {
        assert!(clean(source), "{source}");
    }
    for source in [
        "import types\nU = getattr(types, 'FunctionType')\n",
        "import types\nU = getattr(types, 'CodeType', None)\n",
        "import types\ndef f(name):\n    return getattr(types, name)\n",
        "import types\nU = getattr(types, 'Union' + 'Type')\n",
        "import types\nU = getattr(types, *names)\n",
        "import types\nU = getattr(types, name='UnionType')\n",
        "import sys\nM = getattr(sys, 'modules')\n",
        "import sys\nM = getattr(sys, 'meta_path')\n",
        "def getattr(a, b):\n    return a\nimport types\nU = getattr(types, 'UnionType')\n",
    ] {
        assert!(!clean(source), "{source}");
    }
}

/// The namespace of a frame is read like the namespace of a function (AD-530): a lookup of a
/// literal key is inert; a write, an iteration and a computed key are not.
#[test]
fn a_frame_namespace_follows_the_rules_of_a_function_namespace() {
    for source in [
        "def f(frame):\n    return frame.f_globals.get('__name__')\n",
        "def f(frame):\n    return frame.f_globals['__name__']\n",
        "def f(frame):\n    return '__name__' in frame.f_globals\n",
    ] {
        assert!(clean(source), "{source}");
    }
    for source in [
        "def f(frame):\n    frame.f_globals['sub'] = 1\n",
        "def f(frame, key):\n    return frame.f_globals[key]\n",
        "def f(frame):\n    return list(frame.f_globals.items())\n",
        "def f(frame):\n    return frame.f_globals\n",
    ] {
        assert!(!clean(source), "{source}");
    }
}
