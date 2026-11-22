# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa
"""Plants of the second counter-example run of #1968 (AD-1058): CPython 3.12 imports app.lib."""

import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
P = {}
HEAD = "from importlib import import_module\n_LZ = {'first': (__spec__.parent, '.first'), 'second': (__spec__.parent, '.second')}\n"
OTH = {"src/app/first.py": "first = 1\n", "src/app/second.py": "second = 1\n"}


def mk(body, tail="", others=None):
    return ("", {"src/app/__init__.py": HEAD + body + tail, **OTH, **(others or {})})


P["S1 return getattr(import_module(module, package=package), name)"] = mk(
    "def __getattr__(name):\n    value = _LZ.get(name)\n    if value is None:\n        raise AttributeError(name)\n    package, module = value\n    return getattr(import_module(module, package=package), name)\n"
)
P["S2 return import_module only"] = mk(
    "def __getattr__(name):\n    value = _LZ.get(name)\n    if value is None:\n        raise AttributeError(name)\n    package, module = value\n    return import_module(module, package=package)\n"
)
P["S3 getattr with literal"] = mk(
    "def __getattr__(name):\n    value = _LZ.get(name)\n    if value is None:\n        raise AttributeError(name)\n    package, module = value\n    return getattr(import_module(module, package=package), 'first')\n"
)
