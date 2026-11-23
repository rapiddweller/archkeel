// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The standard library names that import a module by a string or hand out a code object
//! (AD-1059, #1969, #1970). The names resolve through the import bindings of the module: the same
//! name on a project function or method is no site. CPython runs the plants of the same forms in
//! `tests/test_collector_false_pass_python_stdlib_importers.py`.

use super::*;

fn details(source: &str) -> Vec<String> {
    clear_details(source)
}

#[test]
fn a_standard_library_importer_by_a_string_is_a_site_in_each_binding_form() {
    for source in [
        "import logging.config\nlogging.config.dictConfig({})\n",
        "import logging.config as lc\nlc.dictConfig({})\n",
        "from logging.config import dictConfig as dc\ndc({})\n",
        "from logging import config\nconfig.fileConfig('x.ini')\n",
        "from logging.config import *\ndictConfig({})\n",
        "import unittest\nunittest.TestLoader().loadTestsFromName('a')\n",
        "import unittest as u\nu.defaultTestLoader.loadTestsFromNames(['a'])\n",
        "from unittest import TestLoader as L\nL().discover('t')\n",
        "from unittest.loader import defaultTestLoader\n",
        "import unittest\nunittest.main(module='a')\n",
        "import unittest\nunittest.main(module=None, argv=['x', 'a'])\n",
        "import unittest\nunittest.main(defaultTest='a')\n",
        "import unittest\nunittest.main('a')\n",
        "import unittest\nunittest.main(**options)\n",
        "import unittest\nunittest.main(*arguments)\n",
        "import unittest\nunittest.TestProgram(module='a')\n",
        "import unittest\nrun = unittest.main\n",
        // The import of the name is the site: a later call cannot show its arguments.
        "from unittest import main as m\nm(module='a')\n",
        "from unittest import *\n",
        "import xml.sax\nxml.sax.make_parser(['a'])\n",
        "import xml.sax\nxml.sax.make_parser(parser_list=['a'])\n",
        "from xml.sax import make_parser\n",
        "import xml.sax\nxml.sax._create_parser('a')\n",
        "import dis\ndis.Bytecode(f).codeobj\n",
        "import dis\nlist(dis.get_instructions(f))\n",
        "import dis as d\nd._get_code_object(f)\n",
        "from dis import Bytecode\n",
        "from dis import *\n",
        "import inspect\ninspect.dis.get_instructions(f)\n",
        "import cProfile\ncProfile.run('import a')\n",
        "import cProfile\ncProfile.Profile().run('import a')\n",
        "import profile\nprofile.runctx('import a', {}, {})\n",
        "import trace\ntrace.Trace().run('import a')\n",
        "import bdb\nclass B(bdb.Bdb): ...\n",
        "import pdb\npdb.run('import a')\n",
        "help('a')\n",
        "import warnings\nwarnings._setoption('ignore::a.X')\n",
        "import multiprocessing.spawn\nmultiprocessing.spawn.prepare({})\n",
        // A star import binds a hazard name that the module holds directly.
        "from sys import *\n",
        "from unittest.mock import *\n",
    ] {
        assert!(!details(source).is_empty(), "{source}");
    }
}

#[test]
fn a_call_that_names_no_module_and_a_project_name_are_no_site() {
    for source in [
        "import unittest\nunittest.main()\n",
        "import unittest\nunittest.main(verbosity=2, exit=False)\n",
        "import unittest as u\nu.main(failfast=True)\n",
        "import xml.sax\nxml.sax.make_parser()\n",
        "import logging\nlogging.getLogger('x').info('y')\n",
        "import logging.handlers\nh = logging.handlers.RotatingFileHandler\n",
        "import dis\ndis.dis(f)\ndis.opname[1]\n",
        "import pickletools\npickletools.dis(b'N.')\n",
        "from xml.sax.saxutils import escape\n",
        "import unittest\nclass T(unittest.TestCase): ...\nunittest.TextTestRunner()\n",
        "import tracemalloc\ntracemalloc.start()\n",
        "def dictConfig(x):\n    return x\ndictConfig({})\n",
        "class C:\n    def dictConfig(self, x):\n        return x\nC().dictConfig({})\n",
        "class L:\n    def loadTestsFromName(self, n):\n        return n\nL().loadTestsFromName('a')\n",
        "def run(logging):\n    logging.config.dictConfig({})\n",
        "def go(profile):\n    return profile.run()\n",
        "class W:\n    codeobj = 1\nx = W().codeobj\n",
        "import argparse\nargparse.ArgumentParser().add_argument('-x', help='x')\n",
    ] {
        assert_eq!(details(source), Vec::<String>::new(), "{source}");
    }
}

#[test]
fn a_star_import_of_a_module_that_holds_no_hazard_name_is_no_site() {
    for source in ["from os.path import *\n", "from collections import *\n"] {
        assert_eq!(details(source), Vec::<String>::new(), "{source}");
    }
}
