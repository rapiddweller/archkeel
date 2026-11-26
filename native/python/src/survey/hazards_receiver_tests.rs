// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Receiver proofs of a computed attribute name (AD-1053, AD-1058, #1967). Each plant of the
//! first list is a site: a trojan horse is a place that can load code the scan does not see. Each
//! plant of the second list is proven and gives no site. CPython runs the plants of the same
//! forms in `tests/test_collector_false_pass_python_trojan_attribute.py`.

use super::*;

fn trojan_names(source: &str) -> Vec<String> {
    clear_details(source)
}

#[test]
fn a_computed_attribute_name_on_an_unproved_receiver_is_a_site() {
    for source in [
        "def f(x, n):\n    return getattr(x, n)\n",
        "def f(x, n):\n    return getattr(x, '__co' + 'de__')\n",
        "def f(x, n):\n    setattr(x, n, 1)\n",
        "def f(x, n):\n    return x.__getattribute__(n)\n",
        "def f(x, n):\n    return object.__getattribute__(x, n)\n",
        "def g(): ...\ndef f(n):\n    return getattr(g, n)\n",
        "def f(x):\n    n = 'a'\n    n += 'b'\n    return getattr(x, n)\n",
        "def f(x):\n    global n\n    n = 'a'\n    return getattr(x, n)\n",
        "from json import loads\ndef f(n):\n    return getattr(loads, n)\n",
        // AD-1058: a module is no proven receiver; each module has `__builtins__`.
        "import json\ndef f(n):\n    return getattr(json, n)\n",
        "import json as j\ndef f(n):\n    return getattr(j, n)\n",
        "import os.path as m\ndef f(n):\n    return getattr(m, n)\n",
        "def f(n):\n    m = import_module('a')\n    return getattr(m, n)\n",
        // A reference to an access form that is no call that the scan reads is a site.
        "g = getattr\n",
        "def f(x, n):\n    ga = x.__getattribute__\n    return ga(n)\n",
        "def f(xs, n):\n    return list(map(getattr, xs, n))\n",
        "import functools\ndef f(x, n):\n    return functools.partial(getattr, x)(n)\n",
        "import operator\ndef f(x):\n    return operator.attrgetter('a')(x)\n",
        "import operator\ndef f(x, n):\n    return operator.methodcaller(n)(x)\n",
        "def f(m, n):\n    return vars(m)[n]\n",
        "def f(m, n):\n    return m.__dict__[n]\n",
        "def f(m, n):\n    return m.__dict__.get(n)\n",
        "def f(m):\n    return vars(m)\n",
        // AD-1058: no class is a proven receiver (a decorator or a store can replace it).
        "class C: ...\ndef f(n):\n    return getattr(C, n)\n",
        "def d(c):\n    return other\n@d\nclass C: ...\ndef f(n):\n    return getattr(C, n)\n",
        "class C: ...\nimport sys\ndef f(n):\n    return getattr(C, n)\n",
        // An alias hides the later use: the import is the site.
        "from inspect import getmembers as gm\n",
        "from operator import attrgetter as ag\n",
        "from operator import methodcaller as mc\n",
        "from inspect import getattr_static\n",
        "import inspect as i\ndef f(x):\n    return i.getattr_static(x, 'a')\n",
        "def f(x):\n    return x.f_builtins\n",
        "def f(g):\n    return g.gi_frame\n",
        "import sys\ndef f():\n    return sys._getframe(0)\n",
        "import inspect\ndef f():\n    return inspect.currentframe()\n",
        "def f(x):\n    return getattr(x, 'f_builtins')\n",
        // AD-1058: a literal that names reflection is a site (B7 of the third review).
        "import json\ndef f():\n    return getattr(json, '__dict__')\n",
        "def f(x):\n    return getattr(x, '__getattribute__')\n",
        "def f(x):\n    return getattr(x, '__class__')\n",
        "def f(x):\n    n = '__dict__'\n    return getattr(x, n)\n",
        "def f(x):\n    return x.__getattribute__('__dict__')\n",
        "def f(x):\n    return getattr(x, 'getattr')\n",
        "def f(m):\n    d = m.__dict__\n    return d\n",
        "import json\nd = vars(json)\n",
        "def f(n, xs):\n    m = import_module('a')\n    for m in xs:\n        pass\n    return getattr(m, n)\n",
        "def f(n, g):\n    m = import_module('a')\n    m = g()\n    return getattr(m, n)\n",
        // AD-1058: `self` and `cls` are no proof (`C.get(f, n)` passes any first argument).
        "class C:\n    def m(self, n):\n        return getattr(self, n)\n",
        "class C:\n    def m(self, n, v):\n        setattr(self, n, v)\n",
        "class C:\n    @classmethod\n    def m(cls, n):\n        return getattr(cls, n)\n",
        "class C:\n    def m(self, n):\n        self = other\n        return getattr(self, n)\n",
        "class C:\n    @staticmethod\n    def m(self, n):\n        return getattr(self, n)\n",
        // A nested function and a lambda have no proof; a parameter rebinds the name.
        "def f(o, n):\n    m = import_module('a')\n    return (lambda m: getattr(m, n))(o)\n",
        "def f(o, n):\n    m = import_module('a')\n    def g(m):\n        return getattr(m, n)\n    return g(o)\n",
        "def f(o, n, v):\n    def g(s):\n        setattr(s, n, v)\n    g(o)\n",
        // Each binder of the name counts: a pattern, an `except` target, a loop target, a `with`
        // target, a walrus, a nested name, an import and a `del`.
        "def f(o, n):\n    m = import_module('a')\n    match o:\n        case m:\n            return getattr(m, n)\n",
        "def f(o, n):\n    m = import_module('a')\n    try:\n        pass\n    except E as m:\n        pass\n    return getattr(m, n)\n",
        "def f(o, n):\n    m = import_module('a')\n    with o as m:\n        pass\n    return getattr(m, n)\n",
        "def f(o, n):\n    m = import_module('a')\n    (m := o)\n    return getattr(m, n)\n",
        "def f(o, n):\n    m = import_module('a')\n    def m(): ...\n    return getattr(m, n)\n",
        "def f(o, n):\n    m = import_module('a')\n    import b as m\n    return getattr(m, n)\n",
        "def f(o, n):\n    n2 = 'a'\n    del n2\n    n2 = 'b'\n    return getattr(o, n2)\n",
        // The unbound form `C.m(x, n)` has the receiver `x`.
        "class C: ...\ndef f(x, n):\n    return C.__getattribute__(x, n)\n",
        "class C: ...\ndef f(x, n, v):\n    object.__setattr__(x, n, v)\n",
        "class C: ...\ndef f(x, n, v):\n    C.__setattr__(x, n, v)\n",
        "def f(x, n, v):\n    x.__setattr__(n, v)\n",
        // #1979: a write of a literal dunder changes what a later plain call or access runs.
        "class K: ...\nsetattr(K, '__call__', hook)\n",
        "class K: ...\nsetattr(K, '__new__', hook)\n",
        "class K: ...\ndelattr(K, '__call__')\n",
        "class K: ...\nK.__call__ = hook\n",
        "class K: ...\nK.__getattr__ = hook\n",
        "class K: ...\ndel K.__call__\n",
        "class K: ...\nK.__init__ += hook\n",
        "class K: ...\nK.__call__: object = hook\n",
        "class K: ...\nK.__class__, other = hook, 1\n",
        "class K: ...\nfor K.__call__ in [hook]:\n    pass\n",
        "def f(x):\n    x.__class__ = other\n",
        // #2090: the chain names are clear for a write only. A read hands out frames.
        "def f(e):\n    return getattr(e, '__traceback__')\n",
        // #2090: the exemption holds only when the project defines no hook that such a write can reach.
        "class K:\n    def __setattr__(self, n, v):\n        pass\n\n\ndef f(e, c):\n    e.__cause__ = c\n",
        "class K:\n    def __delattr__(self, n):\n        pass\n\n\ndef f(e):\n    del e.__cause__\n",
        "class D:\n    def __set__(self, o, v):\n        pass\n\n\ndef f(e, c):\n    e.__context__ = c\n",
        "class D:\n    def __set_name__(self, o, n):\n        pass\n\n\ndef f(e, c):\n    e.__cause__ = c\n",
        "class K:\n    @property\n    def __cause__(self):\n        return 1\n\n\ndef f(e, c):\n    e.__cause__ = c\n",
        "class K:\n    __notes__ = []\n\n\ndef f(e):\n    e.__notes__ = []\n",
        "class L(list):\n    pass\n\n\ndef f(e):\n    e.__notes__ = L()\n",
        "class T:\n    def __del__(self):\n        pass\n\n\ndef f(e):\n    e.__traceback__ = None\n",
        "K = type('K', (), {'__setattr__': print})\n\n\ndef f(e, c):\n    e.__cause__ = c\n",
        // A write of a dunder that dispatches stays a site beside the chain names.
        "def f(e, c, hook):\n    e.__cause__ = c\n    type(e).__call__ = hook\n",
        "def f(e, c, hook):\n    setattr(e, '__cause__', c)\n    setattr(e, '__getattr__', hook)\n",
    ] {
        // A loader call (`import_module`) is a site of its own; the access is one more.
        let found: Vec<String> = trojan_names(source)
            .into_iter()
            .filter(|name| name != "import_module")
            .collect();
        assert_eq!(found.len(), 1, "{source}: {found:?}");
    }
}

#[test]
fn a_shadowed_builtin_is_no_site() {
    let source = "def getattr(a, b):\n    return a\ndef f(x, n):\n    return getattr(x, n)\n";
    assert!(trojan_names(source).is_empty());
}

#[test]
fn a_literal_name_a_proved_receiver_or_a_local_literal_is_no_site() {
    for source in [
        "def f(x):\n    return getattr(x, 'a')\n",
        "def f(x):\n    return getattr(x, '__name__')\n",
        // A write of a name that no behavior reads: `__doc__`, `__module__` and plain names (#1979).
        "class C: ...\nsetattr(C, '__doc__', 'text')\nC.__module__ = 'm'\nC.value = 1\ndel C.value\n",
        // #2090: Python reads the chain of an exception to print it and never calls it as a hook.
        "def f(e, c):\n    e.__cause__ = c\n    e.__context__ = c\n    e.__traceback__ = None\n    e.__suppress_context__ = True\n    e.__notes__ = []\n",
        "def f(e, c):\n    setattr(e, '__cause__', c)\n    delattr(e, '__context__')\n    object.__setattr__(e, '__cause__', c)\n",
        "def f(e, c):\n    e.__cause__, e.__context__ = c, c\n    e.__notes__ += ['n']\n    del e.__traceback__\n",
        "def f(x):\n    return getattr(x, '__doc__')\n",
        "def f(x):\n    n = 'a'\n    return getattr(x, n)\n",
        "def f(m):\n    return vars(m)['a']\n",
        "def f(m):\n    return m.__dict__['a']\n",
    ] {
        let found = trojan_names(source);
        assert!(found.is_empty(), "{source}: {found:?}");
    }
}
