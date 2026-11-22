# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa
"""Plants of the second counter-example run of #1968 (AD-1058): CPython 3.12 imports app.lib."""

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from python_trojan_plants_1 import F, D, rd, EDIT, PUT

P = {}
# aliases of access forms through from-import
P["A1 from inspect import getmembers as gm (control repeat)"] = rd(
    "from inspect import getmembers as gm\n", "dict(gm(f))"
)
P["A2 from operator import attrgetter as ag"] = rd(
    "from operator import attrgetter as ag\n", "ag(name)(f)"
)
P["A3 from operator import methodcaller as mc"] = rd(
    "from operator import methodcaller as mc\n", "mc('__getattribute__', name)(f)"
)
P["A4 from builtins import getattr as ga"] = rd(
    "from builtins import getattr as ga\n", "ga(f, name)"
)
P["A5 from gc import get_referents as gr"] = (
    "from gc import get_referents as gr\n"
    + F
    + "d = [c for c in gr(f) if type(c) is dict][0]\n"
    + D
)
P["A6 from inspect import getattr_static as gs (get descriptor)"] = rd(
    "from inspect import getattr_static as gs\n", "gs(f, name).__get__(f)"
)
P["A7 inspect.getattr_static plain"] = rd(
    "import inspect\n", "inspect.getattr_static(f, name).__get__(f)"
)
P["A8 from builtins import vars as v"] = rd("from builtins import vars as v\n", "v(f)")
P["A9 import operator as o; o.attrgetter alias var"] = rd(
    "import operator as o\n", "o.attrgetter(name)(f)"
)
P["A10 from functools import reduce; reduce(getattr)"] = rd(
    "from functools import reduce\n", "reduce(getattr, [name], f)"
)
P["A11 f_builtins via getattr literal"] = (
    "import sys\nb = getattr(sys._getframe(0), 'f_builtins')\nb['__imp'+'ort__']('app.lib')\n"
)
P["A12 frame f_back f_builtins"] = (
    "import sys\nsys._getframe().f_builtins['__imp'+'ort__']('app.lib')\n"
)
P["A13 cr_frame/ag_frame f_builtins"] = (
    "async def co():\n    pass\nc = co()\nc.cr_frame.f_builtins['__imp'+'ort__']('app.lib')\nc.close()\n"
)
P["A14 types.FunctionType.__builtins__ (3.10+ function.__builtins__)"] = (
    F + "f.__builtins__['__imp'+'ort__']('app.lib')\n"
)
P["A15 f.__builtins__ via lambda"] = "(lambda: 0).__builtins__['__imp'+'ort__']('app.lib')\n"
P["A16 inspect.getclosurevars(f).builtins"] = (
    "import inspect\ndef g():\n    return 1\ninspect.getclosurevars(g).builtins\nimport sys\nsys._getframe().f_builtins['__imp'+'ort__']('app.lib')\n"
)
P["A17 co_names via f.__code__ literal control"] = F + "c = f.__code__\n"
# class receivers
CL = "class C:\n    pass\n\n"
P["R1 globals()['C']=f"] = (
    F
    + CL
    + "name='__co'+'de__'\nglobals()['C'] = f\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R2 setattr(sys.modules[__name__],'C',f)"] = (
    F
    + CL
    + "import sys\nname='__co'+'de__'\nsetattr(sys.modules[__name__], 'C', f)\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R3 global C in func then call"] = (
    F
    + CL
    + "name='__co'+'de__'\ndef r():\n    global C\n    C = f\nr()\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R4 class decorator returns f"] = (
    F
    + "def dec(c):\n    return f\n@dec\nclass C:\n    pass\nname='__co'+'de__'\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R5 lambda decorator"] = (
    F
    + "@(lambda c: f)\nclass C:\n    pass\nname='__co'+'de__'\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R6 C = D in conditional"] = (
    F
    + CL
    + "name='__co'+'de__'\nif True:\n    C = f\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R7 nested scope param C"] = (
    F
    + CL
    + "name='__co'+'de__'\ndef r(C):\n    return getattr(C, name)\ncode = r(f)\ndef w(C):\n    setattr(C, name, "
    + PUT
    + ")\nw(f)\nf()\n"
)
P["R8 comprehension target C"] = (
    F
    + CL
    + "name='__co'+'de__'\ncode = [getattr(C, name) for C in [f]][0]\n[setattr(C, name, "
    + PUT
    + ") for C in [f]]\nf()\n"
)
P["R9 type('C',(),{}) assignment"] = (
    F + "C = type('C', (), {})\nname='__co'+'de__'\ncode = getattr(C, name)\n"
)
P["R10 class-body class attr: class K: C = f ; getattr(K.C...)"] = (
    F
    + "class K:\n    C = f\nname='__co'+'de__'\ncode = getattr(K.C, name)\nsetattr(K.C, name, "
    + PUT
    + ")\nf()\n"
)
P["R11 getattr(C, n) -> __mro__ then subclasses via non-flag"] = (
    CL + "n='__mr'+'o__'\nobj = getattr(C, n)[-1]\nc = [c for c in obj.__subclasses__()]\n"
)
P["R12 getattr(C,'__init__') literal then .__globals__ computed"] = (
    CL + "n='__ini'+'t__'\nm = getattr(C, n)\n"
)
P["R13 setattr(C, n, v) writes class attr used as module function"] = (
    "import json\nclass C:\n    pass\nn = 'x'\nsetattr(C, 'dump'+'s', lambda *a: __import__('app.lib'))\nC.dumps()\n"
)
P["R14 class C with __getattr__ metaclass returning attr of f"] = (
    F
    + "class M(type):\n    def __getattribute__(cls, n):\n        return type.__getattribute__(cls, n)\nclass C(metaclass=M):\n    fn = f\nname='__co'+'de__'\ncode = getattr(C.fn, name)\n"
)
P["R15 __class__ assignment obj.__class__=Other, getattr(obj)"] = (
    F + "class A:\n    pass\nclass B:\n    pass\nC = A\nA.__class__ = type(f)\n"
    if False
    else F
    + "class A: pass\nclass B(A): pass\nname='__co'+'de__'\nB.__class__ = type\ncode = getattr(B, name)\n"
)
P["R16 __init_subclass__ rebinding module C"] = (
    F
    + "class Base:\n    def __init_subclass__(cls, **kw):\n        globals()['C'] = f\nclass C:\n    pass\nclass Sub(Base):\n    pass\nname='__co'+'de__'\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R17 vars(sys.modules[__name__])['C']=f"] = (
    F
    + CL
    + "import sys\nvars(sys.modules[__name__])['C'] = f\nname='__co'+'de__'\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R18 exec('C = f')"] = (
    F
    + CL
    + "exec('C = f')\nname='__co'+'de__'\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R19 from other module: other sets app.consumer.C"] = (
    F
    + CL
    + "name='__co'+'de__'\nimport app.consumer as me\nme.C = f\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R20 setattr(me,'C',f) via import self"] = (
    F
    + CL
    + "name='__co'+'de__'\nimport app.consumer as me\nsetattr(me, 'C', f)\ncode = getattr(C, name)\nsetattr(C, name, "
    + PUT
    + ")\nf()\n"
)
P["R21 class C defined in if/else (one class binder) but C also def'd"] = (
    F
    + "if True:\n    class C:\n        pass\nelse:\n    C = f\nname='__co'+'de__'\ncode = getattr(C, name)\n"
)
P["R22 C is class; instance method resolves local lit name '__code__'"] = (
    F + "def r():\n    n = '__code__'\n    return getattr(f, n)\ncode = r()\n"
)
P["R23 local lit '__globals__'"] = (
    F + "def r():\n    n = '__globals__'\n    return getattr(f, n)\nd = r()\n" + D
)
P["R24 local lit '__builtins__' on module"] = (
    "import sys\ndef r():\n    n = '__builtins__'\n    return getattr(sys.modules[__name__], n)\nr()['__imp'+'ort__']('app.lib')\n"
)
