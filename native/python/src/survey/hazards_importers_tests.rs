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

#[test]
fn a_string_annotation_is_read_as_code_and_a_hazard_in_it_is_a_site() {
    for source in [
        "class K:\n    x: \"__import__('a.b')\"\n",
        "def f(x: \"__import__('a.b')\"): ...\n",
        "def f() -> \"__import__('a.b')\": ...\n",
        "def f(*, x: \"__import__('a.b')\" = 1): ...\n",
        "x: \"List[__import__('a.b')]\" = []\n",
        "x: List[\"__import__('a.b')\"] = []\n",
        "import unittest\nx: \"unittest.main(module='a')\"\n",
        "from typing import ForwardRef\nForwardRef(\"__import__('a.b')\")\n",
        "import typing\ntyping.ForwardRef(\"eval('x')\")\n",
    ] {
        assert!(!details(source).is_empty(), "{source}");
    }
}

#[test]
fn a_string_annotation_without_a_hazard_and_a_literal_value_are_no_site() {
    for source in [
        "x: \"List[int]\" = []\n",
        "x: \"Annotated[int, Field(gt=0)]\"\n",
        "def f(x: \"Foo\") -> \"Bar\": ...\n",
        "from typing import Literal\nx: Literal[\"eval\", \"exec\"]\n",
        "import typing\nx: typing.Literal[\"help\"]\n",
        "x: \"not valid code (\"\n",
        "x: \"a b\"\n",
        "from typing import ForwardRef\nForwardRef(\"Foo\")\n",
        "s = \"__import__('a.b')\"\n",
    ] {
        assert_eq!(details(source), Vec::<String>::new(), "{source}");
    }
}

#[test]
fn a_text_over_the_parser_bound_a_run_time_write_and_a_string_variable_are_sites() {
    let nest = format!(
        "x: \"{}__import__('a.b'){}\"\n",
        "[".repeat(150),
        "]".repeat(150)
    );
    for source in [
        nest.as_str(),
        "class K: ...\nK.__annotations__ = {'x': 'int'}\n",
        "def f(): ...\nf.__annotations__['x'] = 'int'\n",
        "K.__annotations__.update(x='int')\n",
        "s = \"__import__('a.b')\"\nclass K:\n    x: s\n",
        "s = 'a' + 'b'\nclass K:\n    x: s\n",
        "J = \"list[J]\"\ndef f(x: J): ...\n",
        "J = \"list[Ｊ]\"\ndef f(x: J): ...\n",
        "class C:\n    s = \"list[C.s]\"\nclass K:\n    x: C.s\n",
        "J = \"list['J']\"\ndef f(x: J): ...\n",
        "A = \"B\"\nB = \"A\"\ndef f(x: A): ...\n",
        "A = \"B\"\nB = \"__import__('a.b')\"\ndef f(x: A): ...\n",
    ] {
        assert!(!details(source).is_empty(), "{source}");
    }
}

#[test]
fn a_read_of_annotations_and_a_name_without_a_string_are_no_site() {
    for source in [
        "class K: ...\nprint(K.__annotations__)\n",
        "s = 'int'\nclass K:\n    x: s\n",
        "class A: ...\nclass K:\n    x: A\n",
    ] {
        assert_eq!(details(source), Vec::<String>::new(), "{source}");
    }
}

#[test]
fn many_equal_texts_of_one_name_cost_no_more_than_one() {
    let source = format!("{}class K:\n    x: s\n", "s = 'int'\n".repeat(3000));
    assert_eq!(details(&source), Vec::<String>::new());
    let distinct: String = (0..40).map(|n| format!("s = 'int{n}'\n")).collect();
    assert!(!details(&format!("{distinct}class K:\n    x: s\n")).is_empty());
}

#[test]
fn a_name_with_many_different_texts_stops_collecting() {
    let many: String = (0..40_000).map(|n| format!("s = 'int{n}'\n")).collect();
    let start = std::time::Instant::now();
    assert!(!details(&format!("{many}class K:\n    x: s\n")).is_empty());
    assert!(start.elapsed().as_secs() < 5);
}

#[test]
fn a_module_that_evaluates_annotations_holds_each_value_it_cannot_name() {
    let head = "import typing\ntyping.get_type_hints(K)\n";
    for body in [
        "class K: ...\nprint(K.__annotations__.update(x='int'))\n",
        "class K: ...\na = K.__annotations__\n",
        "K = type('K', (), {'__annotations__': {}})\n",
        "s, t = 'a', 'b'\nclass K:\n    x: s\n",
        "s = 'a'\ns += 'b'\nclass K:\n    x: s\n",
        "for s in ['a']: ...\nclass K:\n    x: s\n",
        "(s := 'a')\nclass K:\n    x: s\n",
        "s = str('a')\nclass K:\n    x: s\n",
        "d = {}\nclass K:\n    x: d['a']\n",
        "class K:\n    x: str('a')\n",
        "K = typing.TypedDict('K', {'x': 'int'})\n",
        "r = typing.ForwardRef(s)\n",
        "class C:\n    s = 'int'\n    s = f()\nclass K:\n    x: C.s\n",
    ] {
        let source = format!("{head}{body}");
        assert!(!details(&source).is_empty(), "{source}");
    }
}

#[test]
fn a_module_that_evaluates_annotations_keeps_plain_type_forms_clean() {
    let head = "import typing\ntyping.get_type_hints(K)\n";
    for body in [
        "class K:\n    x: int\n    y: typing.Optional[str]\n    z: list[int] | None\n",
        "A = list[int]\nT = typing.TypeVar('T')\nclass K:\n    x: A\n    y: T\n",
        "class K:\n    x: typing.Annotated[int, f('meta')]\n",
        "class A: ...\ndef f(a: A) -> A: ...\n",
        "s = 'int'\nclass K:\n    x: s\n",
    ] {
        let source = format!("{head}{body}");
        assert_eq!(details(&source), Vec::<String>::new(), "{source}");
    }
    // No evaluator in the module: a read of `__annotations__` is no site.
    assert_eq!(
        details("class K: ...\nprint(K.__annotations__)\n"),
        Vec::<String>::new()
    );
}

#[test]
fn a_long_chain_of_aliases_costs_no_more_than_one_pass() {
    let mut source = String::from("import typing\ntyping.get_type_hints(K)\ns0 = str('int')\n");
    for n in 1..30_000 {
        source.push_str(&format!("s{n} = s{}\n", n - 1));
    }
    source.push_str("class K:\n    x: s29999\n");
    let start = std::time::Instant::now();
    assert!(!details(&source).is_empty());
    assert!(start.elapsed().as_secs() < 5);
}
