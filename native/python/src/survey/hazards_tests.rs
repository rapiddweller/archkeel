// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: each site becomes a gap of the survey (AD-450). A missed site can hide an edge, so
// each plant of the proof review has a case, and each clean neighbour too.

use super::*;

fn kinds(source: &str) -> Vec<&'static str> {
    let tree = crate::test_tree(source, 14).expect("valid probe");
    sites(&tree).into_iter().map(|site| site.kind).collect()
}

fn has(source: &str, kind: &str) -> bool {
    kinds(source).contains(&kind)
}

#[test]
fn an_alias_value_or_attribute_of_an_import_function_is_a_dynamic_import() {
    for source in [
        "import importlib\nimportlib.import_module(name)\n",
        "import_module(name)\n",
        "from importlib import import_module as load\nload('app.service')\n",
        "import importlib\nload = importlib.import_module\nload('app.service')\n",
        "import importlib\ngetattr(importlib, 'import_' + 'module')('app.service')\n",
        "import builtins\nbuiltins.exec('import app.service')\n",
        "run = exec\nrun('import app.service')\n",
        "f = __import__\nf('app.service')\n",
        "__import__(name)\n",
        "eval(text)\n",
        "loader.load_module(name)\n",
        "spec.loader.exec_module(module)\n",
        "import importlib.util\nimportlib.util.module_from_spec(spec)\n",
        "import os\nos.sys.modules\n",
        "x = __builtins__\n",
        "def later():\n    class Inner:\n        x = __import__(name)\n",
    ] {
        assert!(has(source, DYNAMIC), "{source}");
    }
}

#[test]
fn each_standard_library_door_is_a_dynamic_import() {
    for source in [
        "compile(text, 'f', 'exec')\n",
        "import types\ntypes.FunctionType(code, {})\n",
        "import types\ntypes.CodeType(*parts)\n",
        "import pkgutil\npkgutil.resolve_name('a.b:c')\n",
        "from pydoc import locate\nlocate('a.b')\n",
        "import importlib\nimportlib.reload(module)\n",
        "from importlib.metadata import entry_points\nentry_points()\n",
        "import importlib.metadata\nimportlib.metadata.entry_points()\n",
        "import ctypes\nctypes.pythonapi\n",
        "import pickle\npickle.loads(data)\n",
        "from pickle import Unpickler\n",
        "import marshal\n",
        "import shelve\nshelve.open(path)\n",
        "import dill\n",
        "import timeit\ntimeit.timeit('import app')\n",
        "import doctest\ndoctest.testmod()\n",
        "import code\ncode.interact()\n",
        "import codeop\n",
        "import runpy\nrunpy.run_path(path)\n",
        "from unittest import mock\nmock.patch('app.service.VALUE')\n",
        "from unittest.mock import patch\n",
        "import zipimport\n",
        "import imp\n",
    ] {
        assert!(has(source, DYNAMIC), "{source}");
    }
}

#[test]
fn each_reference_to_the_import_state_is_an_import_system_change() {
    for source in [
        "import sys\nsys.path.insert(0, 'x')\n",
        "import sys as s\ns.path.insert(0, 'x')\n",
        "from sys import path\npath.insert(0, 'x')\n",
        "import sys\nsys.path.__setitem__(0, 'x')\n",
        "import sys\nsys.path.sort()\n",
        "import sys\nsys.path, x = values\n",
        "import sys\nfor sys.path in values:\n    pass\n",
        "import sys\nwith manager as sys.path:\n    pass\n",
        "import sys\nsys.modules['x'] = module\n",
        "import sys\nx = sys.modules.get('x')\n",
        "import sys\nsys.meta_path.append(finder)\n",
        "import site\nsite.addsitedir('x')\n",
        "__path__ = paths\n",
        "import pkg\npkg.__path__ = paths\n",
        "finder.path_hooks.append(hook)\n",
    ] {
        assert!(has(source, IMPORT_SYSTEM), "{source}");
    }
    for source in [
        "import sys\nsetattr(sys, 'path', [])\n",
        "import sys\nvars(sys)\n",
    ] {
        assert!(has(source, DYNAMIC), "{source}");
    }
    let extended = kinds("import pkgutil\n__path__ = pkgutil.extend_path(__path__, __name__)\n");
    assert!(extended.len() >= 2, "{extended:?}");
}

#[test]
fn an_unrelated_name_is_no_site() {
    for source in [
        "model.eval()\nself.exec()\n",
        "import os\nos.path.join(a, b)\n",
        "import re\nre.compile(text)\n",
        "import json\njson.loads(text)\n",
        "import importlib.metadata\nimportlib.metadata.version('x')\n",
        "import importlib.resources\nimportlib.resources.files('x')\n",
        "import sys\nsys.exit(1)\nsys.argv\n",
        "x = pkg.__path__\n",
        "from os import path\npath.join(a, b)\n",
    ] {
        assert!(kinds(source).is_empty(), "{source}: {:?}", kinds(source));
    }
}
