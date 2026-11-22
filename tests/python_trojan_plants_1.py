# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa
"""Plants of the second counter-example run of #1968 (AD-1058): CPython 3.12 imports app.lib."""

F = "def f():\n    import json\n    return json\n\n"
D = "b = d['__bui'+'ltins__']\nb['__imp'+'ort__']('app.lib')\n"


def rd(pre, read, name="'__glo'+'bals__'"):
    return pre + F + f"name = {name}\nd = {read}\n" + D


EDIT = "tuple('app.lib' if n == 'json' else n for n in code.co_names)"
PUT = "code.replace(co_names=" + EDIT + ")"
P = {}
# controls
P["J0 globals() control"] = "d = globals()\n" + D
P["J1 literal f.__globals__ control"] = rd("", "f.__globals__")
P["J2 getattr control"] = rd("", "getattr(f, name)")
# (2) value-use forms
P["V1 import builtins as b; b.getattr"] = rd("import builtins as bb\n", "bb.getattr(f, name)")
P["V2 __builtins__['getattr']"] = rd("", "__builtins__['getattr'](f, name)")
P["V3 __builtins__.__dict__ (dict in module)"] = (
    rd("", "__builtins__['__dict__']['getattr'](f, name)")
    if False
    else rd("", "vars(__builtins__)")
)
P["V4 operator.methodcaller('__getattribute__',n)"] = rd(
    "import operator\n", "operator.methodcaller('__getattribute__', name)(f)"
)
P["V5 (lambda: getattr)()"] = rd("", "(lambda: getattr)()(f, name)")
P["V6 type(f).__getattribute__(f,n)"] = rd("", "type(f).__getattribute__(f, name)")
P["V7 object.__getattribute__"] = rd("", "object.__getattribute__(f, name)")
P["V8 dict.__getitem__(vars(m),n)"] = (
    "import sys\nm = sys.modules[__name__]\nd = dict.__getitem__(vars(m), '__bui'+'ltins__')\nd['__imp'+'ort__']('app.lib')\n"
)
P["V9 inspect.getattr_static"] = rd("import inspect\n", "inspect.getattr_static(f, name)")
P["V10 SimpleNamespace(**vars(m))"] = (
    "import types, sys\nns = types.SimpleNamespace(**vars(sys.modules[__name__]))\nns.__builtins__['__imp'+'ort__']('app.lib')\n"
)
P["V11 functools.reduce(getattr,..)"] = rd(
    "import functools\n", "functools.reduce(getattr, [name], f)"
)
P["V12 itertools.starmap(getattr)"] = rd(
    "import itertools\n", "next(itertools.starmap(getattr, [(f, name)]))"
)
P["V13 sys._getframe(0).f_globals"] = "import sys\nd = sys._getframe(0).f_globals\n" + D
P["V14 sys._getframe(0).f_builtins"] = (
    "import sys\nsys._getframe(0).f_builtins['__imp'+'ort__']('app.lib')\n"
)
P["V15 sys._getframe(0).f_locals"] = (
    "import sys\ndef g():\n    pass\nloc = sys._getframe(0).f_locals\nloc['g'].__call__\nd = sys._getframe().f_globals\n"
    + D
)
P["V16 gc.get_objects()"] = (
    "import gc\nd = [o for o in gc.get_objects() if type(o) is dict and '__import__' in o][0]\nd['__imp'+'ort__']('app.lib')\n"
)
P["V17 object.__subclasses__ jailbreak"] = (
    "c = [c for c in object.__subclasses__() if c.__name__ == 'catch_warnings'][0]\nc()._module.__builtins__['__imp'+'ort__']('app.lib')\n"
)
P["V18 inspect.currentframe().f_globals"] = (
    "import inspect\nd = inspect.currentframe().f_globals\n" + D
)
P["V19 traceback frame f_globals"] = (
    "import sys\ntry:\n    1/0\nexcept Exception:\n    d = sys.exc_info()[2].tb_frame.f_globals\n"
    + D
)
P["V20 gen gi_frame.f_builtins"] = (
    "g = (x for x in [1])\ng.gi_frame.f_builtins['__imp'+'ort__']('app.lib')\n"
)
P["V21 copy.copy(f)+ pickle"] = rd("import copy\n", "copy.copy(f).__dict__")  # control-ish
P["V22 dataclasses.asdict / fields"] = (
    "import dataclasses\n@dataclasses.dataclass\nclass K:\n    x: int = 1\nd = dataclasses.asdict(K())\n"
    + D.replace("d['__bui'", "globals()['__bui'")
)
P["V23 f.__globals__ via operator.itemgetter on __dict__"] = (
    "import operator, sys\nd = operator.itemgetter('__dict__')(sys.modules)\n" + D
)
P["V24 type.__dict__ getset __globals__ via types.FunctionType.__globals__"] = (
    "import types\nd = types.FunctionType.__dict__['__globals__'].__get__(lambda: 0)\n" + D
)
P["V25 f.__call__.__self__"] = rd("", "f.__call__.__self__.__globals__")
P["V26 (lambda:0).__getattribute__"] = rd("", "f.__getattribute__(name)")
P["V27 vars(f)"] = rd("", "vars(f)")
P["V28 __import__ via sys.modules['builtins'] literal"] = (
    "import sys\nsys.modules['builtins'].__import__('app.lib')\n"
)
P["V29 sys.modules['builtins'] computed key"] = (
    "import sys\nsys.modules['built'+'ins'].__import__('app.lib')\n"
)
P["V30 inspect.getmembers alias"] = rd("from inspect import getmembers as gm\n", "dict(gm(f))")
P["V31 inspect.getmembers via module alias inspect as i"] = rd(
    "import inspect as i\n", "dict(i.getmembers(f))"
)
P["V32 inspect.getmembers_static"] = rd("import inspect\n", "dict(inspect.getmembers_static(f))")
P["V33 dir(f)+getattr via stored alias in dict"] = rd(
    "", "{n: getattr(f, n) for n in dir(f)}['__globals__']"
)
P["V34 f.__reduce__"] = rd("import pickle\n", "f.__reduce__")  # control: bogus
