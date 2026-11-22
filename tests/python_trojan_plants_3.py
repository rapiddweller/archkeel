# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa
"""Plants of the second counter-example run of #1968 (AD-1058): CPython 3.12 imports app.lib."""

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from python_trojan_plants_1 import F, D, rd, EDIT, PUT

P = {}
PUBF = {"src/app/pub.py": "value = 2\ndef thing(): ...\n"}
LZ = "from importlib import import_module\n_T = {'pub': '.pub'}\n"
FN = lambda body: (
    "def __getattr__(name):\n    target = _T.get(name)\n    if target is None:\n        raise AttributeError(name)\n"
    + body
)
P["L0 lazy control proper"] = (
    LZ
    + FN("    return import_module(target, package='app')\n")
    + "import app.consumer as me\n_ = me.pub\n",
    PUBF,
)
# getattr in the function body with an arbitrary receiver and name
P["L1 getattr(f, computed) inside lazy __getattr__"] = (
    F
    + LZ
    + FN(
        "    n = '__glo'+'bals__'\n    d = getattr(f, n)\n    b = d['__bui'+'ltins__']\n    b['__imp'+'ort__']('app.lib')\n    return import_module(target, package='app')\n"
    )
    + "__getattr__('pub')\n",
    PUBF,
)
P["L2 getattr(f, computed) read __code__ then via lazy"] = (
    F
    + LZ
    + FN(
        "    code = getattr(f, '__co'+'de__')\n    g = type(f)("
        + PUT
        + ", {})\n    g()\n    return import_module(target, package='app')\n"
    )
    + "__getattr__('pub')\n",
    PUBF,
)
P["L3 getattr(sys.modules, ...) computed module"] = (
    LZ
    + "import sys\n"
    + FN(
        "    m = getattr(sys.modules[__name__], '__bui'+'ltins__')\n    m['__imp'+'ort__']('app.lib')\n    return import_module(target, package='app')\n"
    )
    + "__getattr__('pub')\n",
    PUBF,
)
P["L4 table extended at runtime (T[k]=)"] = (
    LZ
    + "_T['lib'] = '.lib'\n"
    + FN("    return import_module(target, package='app')\n")
    + "__getattr__('lib')\n",
    PUBF,
)
P["L5 table extended at runtime by function elsewhere"] = (
    "from importlib import import_module\n_T = {'pub': '.pub'}\ndef reg(k, v):\n    _T[k] = v\nreg('lib', '.lib')\n"
    + FN("    return import_module(target, package='app')\n")
    + "__getattr__('lib')\n",
    PUBF,
)
P["L6 __getattr__ calls import_module(name) computed"] = (
    "from importlib import import_module\n_T = {'pub': '.pub'}\ndef __getattr__(name):\n    if name in _T:\n        return import_module(_T[name], package='app')\n    return import_module('.'+name, package='app')\n__getattr__('lib')\n",
    PUBF,
)
P["L7 package __getattr__ reads globals()[name]"] = (
    "_T = {'pub': 1}\ndef __getattr__(name):\n    return globals()[name]\n"
    + "globals()['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n",
    PUBF,
)
P["L8 lazy + getattr(x, name) where x=import_module(computed)"] = (
    LZ
    + FN("    mod = import_module(target, package='app')\n    return getattr(mod, name)\n")
    + "import sys\nsys.modules['app.consumer'].pub\n",
    PUBF,
)
P["L9 lazy getattr(mod, name) after setattr on table values"] = (
    F
    + LZ
    + FN("    return getattr(import_module(target, package='app'), name)\n")
    + "_T.update({'lib': '.lib'})\n__getattr__('lib')\n",
    PUBF,
)
P["L10 getattr(f,..) in nested def inside lazy __getattr__"] = (
    F
    + LZ
    + FN(
        "    def inner():\n        d = getattr(f, '__glo'+'bals__')\n        d['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n    inner()\n    return import_module(target, package='app')\n"
    )
    + "__getattr__('pub')\n",
    PUBF,
)
P["L11 getattr in the function: default-arg getattr value"] = (
    F
    + LZ
    + FN(
        "    g = getattr\n    d = g(f, '__glo'+'bals__')\n    d['__bui'+'ltins__']['__imp'+'ort__']('app.lib')\n    return import_module(target, package='app')\n"
    )
    + "__getattr__('pub')\n",
    PUBF,
)
P["L12 getattr(f,'__code__') literal inside lazy fn (control)"] = (
    F
    + LZ
    + FN("    code = getattr(f, '__code__')\n    return import_module(target, package='app')\n")
    + "__getattr__('pub')\n",
    PUBF,
)
P["L13 getattr with module name computed via lazy-ok + sys.modules write"] = (
    LZ
    + FN("    return import_module(target, package='app')\n")
    + "import sys\nm = getattr(sys, 'modu'+'les')\nm['x'] = 1\ngetattr(m['app.consumer'], '__bui'+'ltins__')['__imp'+'ort__']('app.lib')\n",
    PUBF,
)
