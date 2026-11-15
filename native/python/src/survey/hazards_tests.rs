// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: each site becomes a gap of the survey (AD-450). A missed site can hide an edge, so
// each plant of the proof review has a case, and each clean neighbour too.

use super::*;

fn kinds(source: &str) -> Vec<&'static str> {
    let tree = crate::test_tree(source, 14).expect("valid probe");
    sites(
        &tree,
        super::super::literal::Proof::default(),
        &super::super::binders::Binders::of(&tree),
    )
    .into_iter()
    .map(|site| site.kind)
    .collect()
}

fn has(source: &str, kind: &str) -> bool {
    kinds(source).contains(&kind)
}

#[test]
fn only_stable_direct_inert_attribute_loads_lose_their_extra_gap() {
    for (source, import) in [
        (
            "import pickle\nraise pickle.UnpicklingError('bad')\n",
            "pickle",
        ),
        (
            "import pickle as p\ndef f():\n    raise p.UnpicklingError('bad')\n",
            "pickle",
        ),
        ("import pickle\nraise pickle.PickleError('bad')\n", "pickle"),
        ("import pickle\nx = pickle.HIGHEST_PROTOCOL\n", "pickle"),
        (
            "import importlib.metadata as m\nx = m.PackageNotFoundError\n",
            "importlib.metadata",
        ),
        (
            "import importlib.abc as a\nx = a.Traversable\n",
            "importlib.abc",
        ),
    ] {
        let tree = crate::test_tree(source, 14).expect("valid probe");
        let found = sites(&tree, Proof::default(), &Binders::of(&tree));
        assert!(found.iter().any(|site| site.detail == import), "{source}");
        assert_eq!(
            found.iter().filter(|site| site.kind == DYNAMIC).count(),
            1,
            "{source}"
        );
    }
    for source in [
        "import pickle\ndef f(pickle): return pickle.UnpicklingError\n",
        "import pickle\npickle = other\npickle.UnpicklingError\n",
        "if flag:\n    import pickle\npickle.UnpicklingError\n",
        "import pickle\nfrom elsewhere import *\npickle.UnpicklingError\n",
        "import pickle\npickle.UnpicklingError = other\n",
        "import pickle\npickle.UnpicklingError = other\npickle.UnpicklingError()\n",
        "import pickle\npickle.UnpicklingError.__subclasses__()\n",
        "import pickle\npickle.Unpickler\n",
        "import pickle\npickle.loads(data)\n",
    ] {
        let tree = crate::test_tree(source, 14).expect("valid probe");
        let found = sites(&tree, Proof::default(), &Binders::of(&tree));
        assert!(found.len() >= 2, "{source}");
    }
}

#[test]
fn the_other_ce_dynamic_import_forms_keep_their_named_gap() {
    for (source, detail) in [
        ("import pickle\n", "pickle"),
        ("import pickle\npickle.Unpickler\n", "pickle.Unpickler"),
        ("import pickle\npickle.dumps(data)\n", "pickle.dumps"),
        ("import dill\n", "dill"),
        ("import dill\ndill.settings\n", "dill.settings"),
        ("import dill\ndill.Pickler\n", "dill.Pickler"),
        ("import dill\ndill.Unpickler\n", "dill.Unpickler"),
        ("from importlib import metadata\n", "importlib.metadata"),
        (
            "from importlib.resources import files\n",
            "importlib.resources.files",
        ),
        (
            "from importlib.abc import Traversable\n",
            "importlib.abc.Traversable",
        ),
        ("'__builtins__'\n", "__builtins__"),
        ("'__globals__'\n", "__globals__"),
        ("'__import__'\n", "__import__"),
        ("'__loader__'\n", "__loader__"),
        ("'__self__'\n", "__self__"),
        ("'__subclasses__'\n", "__subclasses__"),
        ("eval(text)\n", "eval"),
        ("exec(text)\n", "exec"),
    ] {
        let tree = crate::test_tree(source, 14).expect("valid probe");
        let found = sites(&tree, Proof::default(), &Binders::of(&tree));
        assert!(
            found
                .iter()
                .any(|site| site.kind == DYNAMIC && site.detail == detail),
            "{source}"
        );
    }
}

#[test]
fn the_survey_keeps_the_pickle_import_gap_after_the_exception_read() {
    use crate::survey::targets::tests::{reasons, surveyed};

    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        (
            "src/app/client.py",
            "import pickle\nraise pickle.UnpicklingError('bad')\n",
        ),
    ]);
    let reasons = reasons(&found);
    assert!(reasons
        .iter()
        .any(|reason| reason == "dynamic_import: pickle"));
    assert!(!reasons
        .iter()
        .any(|reason| reason == "dynamic_import: pickle.UnpicklingError"));
}

#[test]
fn literal_hazard_import_keeps_both_edge_and_gap() {
    for source in [
        "code = __import__('code')\n",
        "x = __import__('code')\n",
        "(code := __import__('code'))\n",
        "__import__('code').interact()\n",
        "import importlib\ncode = importlib.import_module('code')\n",
        "f = lambda code=__import__('code'): code\n",
        "def f(code=__import__('code')): return code\n",
        "for code in [__import__('code')]: pass\n",
        "[code for code in [__import__('code')]]\n",
        "with __import__('code') as code: pass\n",
        "try: pass\nexcept __import__('code') as code: pass\n",
        "match __import__('code'):\n    case code: pass\n",
        "f(__import__('code'))\n",
        "@f(__import__('code'))\ndef g(): pass\n",
        "def deco(f): return __import__('code')\n@deco\ndef code(): pass\n",
        "class C:\n    code = __import__('code')\n    def f(self): return self.code\n",
        "def f():\n    global code\n    code = __import__('code')\n",
    ] {
        let tree = crate::test_tree(source, 14).expect("valid probe");
        let binders = Binders::of(&tree);
        let found = sites(&tree, Proof::of(&tree, &binders), &binders);
        assert!(
            found
                .iter()
                .any(|site| site.kind == LITERAL && site.detail == "code"),
            "{source}"
        );
        assert!(
            found
                .iter()
                .any(|site| site.kind == DYNAMIC && site.detail == "code"),
            "{source}"
        );
    }
    for (source, target, kind) in [
        ("__import__('pickle')\n", "pickle", DYNAMIC),
        ("__import__('sys.modules')\n", "sys.modules", IMPORT_SYSTEM),
    ] {
        let tree = crate::test_tree(source, 14).expect("valid probe");
        let binders = Binders::of(&tree);
        let found = sites(&tree, Proof::of(&tree, &binders), &binders);
        assert!(found
            .iter()
            .any(|site| site.kind == LITERAL && site.detail == target));
        assert!(found
            .iter()
            .any(|site| site.kind == kind && site.detail == target));
    }
}

#[test]
fn reflective_code_access_on_imported_module_is_a_gap() {
    for source in [
        "import pdb\ncode = getattr(pdb, 'code')\n",
        "import pdb\ngetattr(pdb, 'code').interact()\n",
        "import pdb\ncode = vars(pdb)['code']\n",
        "import pdb\ncode = pdb.__dict__['code']\n",
        "import pdb\np = pdb\ncode = p.code\n",
        "import pdb\ncode = (p := pdb).code\n",
    ] {
        assert!(has(source, DYNAMIC), "{source}");
    }
    assert!(kinds("def f(provider):\n    return getattr(provider, 'code')\n").is_empty());
}

#[test]
fn local_code_is_not_the_code_module() {
    for source in [
        "def f(code):\n    return code.value\n",
        "def f():\n    code = 'x'\n    return code.replace('x', 'y')\n",
        "def f(items):\n    for code in items: print(code)\n",
        "def f(code):\n    return {'code': code}\n",
        "pickle = obj.pickle\n",
        "self.code.value\n",
    ] {
        assert!(kinds(source).is_empty(), "{source}: {:?}", kinds(source));
    }
    for source in [
        "import code as c\nc.interact()\n",
        "from code import interact as run\nrun()\n",
        "import code\ndef f():\n    code.interact()\n",
    ] {
        assert!(has(source, DYNAMIC), "{source}");
    }
}

#[test]
fn code_received_from_an_unknown_object_is_a_named_limit() {
    assert!(kinds("code = provider.code\ncode.interact()\n").is_empty());
}

#[test]
fn imported_code_and_ambiguous_bindings_remain_gaps() {
    for source in [
        "def f():\n    import code as c\n    def g(): c.interact()\n",
        "if flag:\n    import code\ncode.interact()\n",
        "from package import *\ncode.interact()\n",
        "import code\ndef f():\n    global code\n    code.interact()\n",
        "import code\nx = code\nx.interact()\n",
        "del code\ncode.interact()\n",
        "class C:\n    code.interact()\n",
        "import provider\nprovider.code.interact()\n",
        "from provider import code as c\nc.interact()\n",
        "from . import code as c\nc.interact()\n",
        "getattr(importlib, 'import_module')\n",
        "import sys\nsys.modules['x'] = value\n",
    ] {
        assert!(!kinds(source).is_empty(), "{source}");
    }
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
        "import importlib.metadata\nimportlib.metadata.version('x')\n",
        "from importlib import resources\nresources.files('x')\n",
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
        "import sys\nsys.exit(1)\nsys.argv\n",
        "x = pkg.__path__\n",
        "from os import path\npath.join(a, b)\n",
    ] {
        assert!(kinds(source).is_empty(), "{source}: {:?}", kinds(source));
    }
}

#[test]
fn only_the_inert_names_of_importlib_metadata_are_no_site() {
    let inert = "from importlib.metadata import PackageNotFoundError, version\ntry:\n    v = version('x')\nexcept PackageNotFoundError:\n    v = None\n";
    assert!(kinds(inert).is_empty(), "{:?}", kinds(inert));
    assert!(kinds("from importlib.metadata import version as v\nv('x')\n").is_empty());
    for source in [
        "from importlib.metadata import entry_points\n",
        "from importlib.metadata import distribution\n",
        "from importlib.metadata import metadata\n",
        "from importlib.metadata import files\n",
        "from importlib.metadata import *\n",
        "from importlib import metadata\nmetadata.version('x')\n",
        "import importlib.metadata as md\nmd.version('x')\n",
        "import importlib.metadata\nimportlib.metadata.version('x')\n",
        "from importlib.metadata import version, entry_points\n",
        "from importlib.metadata import version\nversion.__globals__\n",
        "from importlib.metadata import version\nversion.inner\n",
    ] {
        assert!(has(source, DYNAMIC), "{source}");
    }
}
