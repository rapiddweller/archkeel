# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa
"""Plants: the standard library imports a module that a string names. Python 3.12 imports `app.lib`."""

GUARD = "try:\n    {call}\nexcept Exception:\n    pass\n"


def guarded(imports: str, call: str) -> str:
    return imports + GUARD.format(call=call)


P = {
    "logging.config '()' handler": guarded(
        "import logging.config\n",
        "logging.config.dictConfig({'version': 1, 'handlers': {'h': {'()': 'app.lib.X'}}})",
    ),
    "logging.config 'class' handler": guarded(
        "import logging.config\n",
        "logging.config.dictConfig({'version': 1, 'handlers': {'h': {'class': 'app.lib.X'}}})",
    ),
    "logging.config '()' formatter": guarded(
        "import logging.config\n",
        "logging.config.dictConfig({'version': 1, 'formatters': {'f': {'()': 'app.lib.X'}}})",
    ),
    "pkgutil.resolve_name": guarded("import pkgutil\n", "pkgutil.resolve_name('app.lib')"),
    "importlib.resources.files": guarded(
        "import importlib.resources\n", "importlib.resources.files('app.lib')"
    ),
    "unittest.mock.patch": guarded(
        "from unittest import mock\n", "mock.patch('app.lib.value').start()"
    ),
    "unittest loadTestsFromName": guarded(
        "import unittest\n", "unittest.TestLoader().loadTestsFromName('app.lib')"
    ),
    "pydoc.locate": guarded("import pydoc\n", "pydoc.locate('app.lib')"),
    "timeit statement": guarded("import timeit\n", "timeit.timeit('import app.lib', number=1)"),
    "pickle.loads": guarded("import pickle\n", "pickle.loads(b'capp.lib\\nvalue\\n.')"),
    "runpy.run_module": guarded("import runpy\n", "runpy.run_module('app.lib')"),
}
