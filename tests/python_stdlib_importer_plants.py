# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa
"""Plants: the standard library imports a module that a string names. Python 3.12 imports `app.lib`."""

GUARD = "try:\n    {call}\nexcept Exception:\n    pass\n"
# A call that prints (`help`, a profiler, a debugger) writes to a discarded stream: the oracle reads
# the standard output of the child process.
QUIET = (
    "import contextlib\nimport io\n\n{imports}try:\n"
    "    with contextlib.redirect_stdout(io.StringIO()):\n        {call}\nexcept BaseException:\n    pass\n"
)
CONFIG = "{'version': 1, 'handlers': {'h': {'()': 'app.lib.X'}}}"
INI = (
    "[loggers]\\nkeys=root\\n[handlers]\\nkeys=h\\n[formatters]\\nkeys=\\n[logger_root]\\nhandlers=h\\n"
    "[handler_h]\\nclass=app.lib.X\\nargs=()\\n"
)
# `dis` hands the code object of `f` out, and a function built from it imports another module.
CODE = "def f():\n    import json\n    return json\n\n\n"
BUILD = (
    "new = code.replace(co_names=tuple('app.lib' if n == 'json' else n for n in code.co_names))\n"
    "type(f)(new, {})()\n"
)
NESTED = "def f():\n    def h():\n        import json\n        return json\n    return h\n\n\n"


def guarded(imports: str, call: str) -> str:
    return imports + GUARD.format(call=call)


def quiet(imports: str, call: str) -> str:
    return QUIET.format(imports=imports, call=call)


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
    # #1970: the keys '()', 'class', 'filters' and 'ext://' of a logging configuration name a module.
    "logging.config 'filters'": guarded(
        "import logging.config\n",
        "logging.config.dictConfig({'version': 1, 'filters': {'f': {'()': 'app.lib.X'}}})",
    ),
    "logging.config 'ext://'": guarded(
        "import logging.config\n",
        "logging.config.dictConfig({'version': 1, 'handlers': {'h': {'class': "
        "'logging.StreamHandler', 'stream': 'ext://app.lib.X'}}})",
    ),
    "logging.config fileConfig": guarded(
        "import io\nimport logging.config\n",
        f"logging.config.fileConfig(io.StringIO('{INI}'))",
    ),
    "logging.config DictConfigurator": guarded(
        "import logging.config\n",
        f"logging.config.DictConfigurator({CONFIG}).configure()",
    ),
    "logging.config BaseConfigurator.resolve": guarded(
        "import logging.config\n", "logging.config.BaseConfigurator({}).resolve('app.lib.X')"
    ),
    "logging.config alias from-import": guarded(
        "from logging.config import dictConfig as dc\n", f"dc({CONFIG})"
    ),
    "logging.config alias import-as": guarded(
        "import logging.config as lc\n", f"lc.dictConfig({CONFIG})"
    ),
    "logging.config module from-import": guarded(
        "from logging import config\n", f"config.dictConfig({CONFIG})"
    ),
    "logging.config star import": guarded(
        "from logging.config import *\n", f"dictConfig({CONFIG})"
    ),
    "unittest loadTestsFromNames": guarded(
        "import unittest\n", "unittest.TestLoader().loadTestsFromNames(['app.lib'])"
    ),
    "unittest defaultTestLoader": guarded(
        "import unittest\n", "unittest.defaultTestLoader.loadTestsFromName('app.lib')"
    ),
    "unittest loader in a variable": guarded(
        "import unittest\nloader = unittest.TestLoader()\n", "loader.loadTestsFromName('app.lib')"
    ),
    "unittest loader alias": guarded(
        "from unittest import TestLoader as L\n", "L().loadTestsFromName('app.lib')"
    ),
    "unittest discover": guarded(
        "import unittest\n",
        "unittest.TestLoader().discover('src/app', pattern='lib*.py', top_level_dir='src')",
    ),
    "unittest.main module": guarded(
        "import unittest\n", "unittest.main(module='app.lib', exit=False, argv=['x'])"
    ),
    "unittest.main argv": guarded(
        "import unittest\n", "unittest.main(module=None, exit=False, argv=['x', 'app.lib'])"
    ),
    "unittest.TestProgram": guarded(
        "import unittest\n", "unittest.TestProgram(module='app.lib', exit=False, argv=['x'])"
    ),
    "unittest.main alias": guarded(
        "from unittest import main as m\n", "m(module='app.lib', exit=False, argv=['x'])"
    ),
    # #1969: the standard library hands out a code object by a route that has no `__code__`.
    "dis Bytecode codeobj": "import dis\n\n\n" + CODE + "code = dis.Bytecode(f).codeobj\n" + BUILD,
    "dis Bytecode nested constant": (
        "import dis\n\n\n"
        + NESTED
        + "code = [i.argval for i in dis.Bytecode(f) if hasattr(i.argval, 'co_names')][0]\n"
        + BUILD
    ),
    "dis get_instructions nested constant": (
        "import dis\n\n\n"
        + NESTED
        + "code = [i.argval for i in dis.get_instructions(f) if hasattr(i.argval, 'co_names')][0]\n"
        + BUILD
    ),
    "dis _get_code_object": "import dis\n\n\n" + CODE + "code = dis._get_code_object(f)\n" + BUILD,
    "dis alias from-import": (
        "from dis import Bytecode as B\n\n\n" + CODE + "code = B(f).codeobj\n" + BUILD
    ),
    "dis star import": "from dis import *\n\n\n" + CODE + "code = Bytecode(f).codeobj\n" + BUILD,
    "inspect.dis Bytecode": "import inspect\n\n\n"
    + CODE
    + "code = inspect.dis.Bytecode(f).codeobj\n"
    + BUILD,
    # Siblings (CPython 3.12 imports `app.lib` in each one): a string that the library imports or runs.
    "xml.sax.make_parser": guarded("import xml.sax\n", "xml.sax.make_parser(['app.lib'])"),
    "xml.sax.make_parser alias": guarded(
        "from xml.sax import make_parser as mp\n", "mp(parser_list=['app.lib'])"
    ),
    "help": quiet("", "help('app.lib')"),
    "cProfile.run": quiet("import cProfile\n", "cProfile.run('import app.lib')"),
    "cProfile.runctx": quiet("import cProfile\n", "cProfile.runctx('import app.lib', {}, {})"),
    "cProfile.Profile.run": quiet("import cProfile\n", "cProfile.Profile().run('import app.lib')"),
    "profile.run": quiet("import profile\n", "profile.run('import app.lib')"),
    "trace.Trace.run": quiet(
        "import trace\n", "trace.Trace(count=0, trace=0).run('import app.lib')"
    ),
    "bdb.Bdb.run": quiet("import bdb\n", "bdb.Bdb().run('import app.lib')"),
    "pdb.Pdb.run": quiet(
        "import pdb\n",
        "pdb.Pdb(stdin=io.StringIO('c\\n'), stdout=io.StringIO()).run('import app.lib')",
    ),
    "multiprocessing.spawn.prepare": guarded(
        "import multiprocessing.spawn as s\n", "s.prepare({'init_main_from_name': 'app.lib'})"
    ),
    "warnings._setoption": guarded("import warnings\n", "warnings._setoption('ignore::app.lib.X')"),
    "warnings._getcategory": guarded("import warnings\n", "warnings._getcategory('app.lib.X')"),
}

# The code of a project and of the standard library that no rule may refuse: each stays PASS and
# CPython leaves `app.lib` unloaded. The same names on a project object have no import origin.
CONTROLS = {
    "project function dictConfig": "def dictConfig(x):\n    return x\n\n\ndictConfig({})\n",
    "project method dictConfig": (
        "class C:\n    def dictConfig(self, x):\n        return x\n\n\nC().dictConfig({})\n"
    ),
    "project method loadTestsFromName": (
        "class L:\n    def loadTestsFromName(self, n):\n        return n\n\n\n"
        "L().loadTestsFromName('app.lib')\n"
    ),
    "project parameter named logging": "def run(logging):\n    logging.config.dictConfig({})\n",
    "logging getLogger": "import logging\n\nlogging.getLogger('x').info('y')\n",
    "logging handler class": (
        "import logging\n\n\nclass H(logging.Handler):\n    def __init__(self):\n"
        "        logging.Handler.__init__(self)\n\n\nx = getattr(logging, 'INFO')\n"
    ),
    "dis.dis": quiet("import dis\n\n\ndef f():\n    return 1\n\n\n", "dis.dis(f)"),
    "unittest.main()": (
        "import unittest\n\n\nclass T(unittest.TestCase):\n    def test(self):\n        pass\n\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n"
    ),
    "unittest.main(verbosity)": (
        "import unittest\n\nif __name__ == '__main__':\n    unittest.main(verbosity=2)\n"
    ),
    "xml.sax.make_parser()": "import xml.sax\n\nparser = xml.sax.make_parser()\n",
    "xml.sax.saxutils": "from xml.sax.saxutils import escape\n\nx = escape('a')\n",
    "project name profile": "def go(profile):\n    return profile.run()\n",
}
