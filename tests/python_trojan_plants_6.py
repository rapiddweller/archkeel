# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa
"""Plants of the second counter-example run of #1968 (AD-1058): CPython 3.12 imports app.lib."""

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
P = {}
HEAD = "from importlib import import_module\n_LZ = {'first': (__spec__.parent, '.first'), 'second': (__spec__.parent, '.second')}\n"
OTH = {
    "src/app/first.py": "first = 1\n",
    "src/app/second.py": "second = 1\n",
    "src/app/fn.py": "def f():\n    import json\n    return json\n",
}
FN = "def __getattr__(name):\n    value = _LZ.get(name)\n    if value is None:\n        raise AttributeError(name)\n    package, module = value\n%s    return import_module(module, package=package)\n"


def mk(extra="", tail="", others=None, head=HEAD):
    return ("", {"src/app/__init__.py": head + FN % extra + tail, **OTH, **(others or {})})


P["M0 control (S2)"] = mk()
P["M1 getattr(globals-of-function) computed in body"] = mk(
    "    _d = getattr(__getattr__, '__glo'+'bals__')\n    _d['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n",
    "__getattr__('first')\n",
)
P["M2 getattr(import_module-fn) computed"] = mk(
    "    _d = getattr(import_module, '__glo'+'bals__')\n    _d['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n",
    "__getattr__('first')\n",
)
P["M3 getattr(sys...)"] = mk(
    "    import sys\n    _m = getattr(sys, 'modu'+'les')\n    getattr(_m['app'], '__bui'+'ltins__')['__imp'+'ort__']('app.lib')\n",
    "__getattr__('first')\n",
)
P["M4 getattr(value computed) code of fn module"] = mk(
    "    from app.fn import f\n    _c = getattr(f, '__co'+'de__')\n    _g = type(f)(_c.replace(co_names=tuple('app.lib' if n == 'json' else n for n in _c.co_names)), {})\n    _g()\n",
    "__getattr__('first')\n",
)
P["M5 table extension after def (T update) -> lib"] = mk(
    "", "_LZ['lib'] = (__spec__.parent, '.lib')\n__getattr__('lib')\n"
)
P["M6 table extension via setdefault/|= "] = mk(
    "", "_LZ |= {'lib': (__spec__.parent, '.lib')}\n__getattr__('lib')\n"
)
P["M7 table extension in another module"] = mk(
    "",
    "",
    {
        "src/app/consumer.py": "import app\napp._LZ['lib'] = (app.__spec__.parent, '.lib')\napp.lib\n"
    },
)
P["M8 name no key, module attr read by consumer: __getattr__('lib') returns?"] = mk(
    "", "__getattr__('lib')\n"
)
P["M9 package-level getattr(globals()[name]) in 2nd func"] = mk(
    "", "def other(name):\n    return getattr(globals(), name)\n"
)
P["M10 getattr outside __getattr__ (module level) computed"] = mk(
    "",
    "_d = getattr(__getattr__, '__glo'+'bals__')\n_d['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n",
)
P["M11 getattr in lambda inside body"] = mk(
    "    _l = lambda: getattr(import_module, '__glo'+'bals__')\n    _l()['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n",
    "__getattr__('first')\n",
)
P["M12 setattr in body (not exempt?)"] = mk("    setattr(import_module, '__co'+'de__', 1)\n", "")
