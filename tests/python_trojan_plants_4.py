# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa
"""Plants of the second counter-example run of #1968 (AD-1058): CPython 3.12 imports app.lib."""

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
P = {}
INIT = """from importlib import import_module
_LZ = {'first': (__spec__.parent, '.first'), 'second': (__spec__.parent, '.second')}
def __getattr__(name):
    value = _LZ.get(name)
    if value is None:
        raise AttributeError(name)
    package, module = value
%s    if module == '__module__':
        result = import_module(f'.{name}', package=package)
        globals()[name] = result
        return result
    result = import_module(module, package=package)
    for key, (_, item_module) in _LZ.items():
        if item_module == module:
            globals()[key] = getattr(result, key)
    return result
%s"""
OTH = {
    "src/app/first.py": "first = 1\n",
    "src/app/second.py": "second = 1\n",
    "src/app/fn.py": "def f():\n    import json\n    return json\n",
}


def mk(extra="", tail="", others=None):
    return ("", {"src/app/__init__.py": INIT % (extra, tail), **OTH, **(others or {})})


P["LA0 control accepted lazy, no extra"] = mk()
P["LA1 extra getattr(f, computed globals) in body"] = mk(
    "    _d = getattr(f, '__glo'+'bals__')\n    _d['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n",
    "first_ = __getattr__('first')\n",
)
P["LA2 same, trigger via attribute access from consumer"] = mk(
    "    _d = getattr(f, '__glo'+'bals__')\n    _d['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n",
    "",
)
P["LA3 getattr(sys.modules,..) inside"] = mk(
    "    import sys\n    _m = getattr(sys, 'modu'+'les')\n    getattr(_m['app'], '__bui'+'ltins__')['__imp'+'ort__']('app.lib')\n",
    "__getattr__('first')\n",
)
P["LA4 getattr(__import__-less: builtins via globals)"] = mk(
    "    _b = getattr(globals(), 'get')('__bui'+'ltins__')\n    getattr(_b, 'get')('__imp'+'ort__')('app.lib')\n",
    "__getattr__('first')\n",
)
P["LA5 table extended at runtime after the function (key lib)"] = mk(
    "", "_LZ['lib'] = (__spec__.parent, '.lib')\n__getattr__('lib')\n"
)
P["LA6 table extended via update"] = mk(
    "", "_LZ.update({'lib': (__spec__.parent, '.lib')})\n__getattr__('lib')\n"
)
P["LA7 computed key via name that is no key: import_module(f'.{name}')"] = mk(
    "", "__getattr__('lib')\n"
)
P["LA8 module key '__module__' value spec.parent + name lib"] = mk(
    "", "_LZ['lib'] = (__spec__.parent, '__module__')\n__getattr__('lib')\n"
)
P["LA9 package-level __getattr__ reads globals()[name] (not table)"] = (
    "",
    {
        "src/app/__init__.py": "def __getattr__(name):\n    return globals()[name]\ng = globals()\ng['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n",
        **OTH,
    },
)
P["LA10 mutation of table in another module"] = mk(
    "",
    "",
    {
        "src/app/other.py": "import app\napp._LZ['lib'] = (app.__spec__.parent, '.lib')\nimport app as a2\na2.lib\n",
        "src/app/consumer.py": "import app.other\n",
    },
)
P["LA11 getattr(x, n) with x=_LZ values in body (receiver table)"] = mk(
    "    _x = getattr(_LZ, 'ge'+'t')\n    getattr(_x, '__sel'+'f__')\n", "__getattr__('first')\n"
)
P["LA12 body uses getattr to fetch __globals__ of __getattr__ itself"] = mk(
    "    _d = getattr(__getattr__, '__glo'+'bals__')\n    _d['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n",
    "__getattr__('first')\n",
)
