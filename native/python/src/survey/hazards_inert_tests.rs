// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Inert-read and retained-trojan horse plants for the Python import survey.

use super::*;
use crate::module::Module;
use crate::survey::hazards_split::split;

#[path = "hazards_importers_tests.rs"]
mod importers;
#[path = "hazards_proved_tests.rs"]
mod proved;
#[path = "hazards_receiver_tests.rs"]
mod receiver;

#[test]
fn imported_code_types_in_isinstance_keep_the_import_gap() {
    for name in ["FunctionType", "CodeType"] {
        let source = format!("from types import {name}\nx = isinstance(value, {name})\n");
        let tree = crate::test_tree(&source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        let matching: Vec<_> = found
            .iter()
            .filter(|site| site.detail == format!("types.{name}"))
            .collect();
        assert_eq!(matching.len(), 1, "{source}");
        assert!(matching[0].trojan_horse.is_none(), "{source}");
    }
    for source in [
        "from types import FunctionType\nx = FunctionType(code, globals())\n",
        "from types import FunctionType\nFunctionType = other\nx = isinstance(value, FunctionType)\n",
        "from types import FunctionType\nx = FunctionType\n",
        "from types import FunctionType\nisinstance = other\nx = isinstance(value, FunctionType)\n",
        "from types import FunctionType\nfrom elsewhere import *\nx = isinstance(value, FunctionType)\n",
        "from types import FunctionType as F\nx = isinstance(value, F)\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(&tree, Proof::default(), &Binders::of(&tree), &HashSet::new());
        assert!(found.iter().filter(|site| site.detail == "types.FunctionType").count() >= 2, "{source}");
    }
    let source = "from types import FunctionType\nx = isinstance(eval(text), FunctionType)\n";
    let tree = crate::test_tree(source, 12).expect("valid probe");
    let found = sites(
        &tree,
        Proof::default(),
        &Binders::of(&tree),
        &HashSet::new(),
    );
    assert!(found.iter().any(|site| site.detail == "eval"));
}

#[test]
fn direct_metadata_version_reads_keep_the_import_gap() {
    for source in [
        "import importlib.metadata\nx = importlib.metadata.version('pip')\n",
        "import importlib.metadata\nx = importlib.metadata.PackageNotFoundError\n",
        "import importlib.metadata\nx = importlib.metadata.distribution('pip')\n",
        "from importlib import metadata as m\nx = m.distributions()\n",
        "from importlib import metadata as m\nx = m.version('pip')\n",
        "import importlib.metadata as m\nx = m.version('pip')\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert_eq!(
            found
                .iter()
                .filter(|site| site.detail == "importlib.metadata")
                .count(),
            1,
            "{source}"
        );
        assert!(
            found
                .iter()
                .any(|site| site.detail == "importlib.metadata" && site.trojan_horse.is_none()),
            "{source}"
        );
    }
    for source in [
        "import importlib.metadata\nimportlib.metadata.version = replacement\n",
        "import importlib.metadata\nimportlib = other\nx = importlib.metadata.version\n",
        "import importlib.metadata\nfrom elsewhere import *\nx = importlib.metadata.version\n",
        "import importlib.metadata\nx = importlib.metadata.version.other\n",
        "import importlib\nx = importlib.metadata.version\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert!(
            found.iter().any(|site| site.detail == "importlib.metadata"),
            "{source}"
        );
        if !source.starts_with("import importlib\n") {
            assert!(found.len() >= 2, "{source}");
        }
    }
}

#[test]
fn imported_inert_attribute_keeps_its_import_gap() {
    for source in [
        "from importlib.abc import Traversable\ndef f() -> Traversable: pass\n",
        "from importlib.abc import Traversable as T\ndef f() -> T: pass\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert_eq!(
            found
                .iter()
                .filter(|site| site.detail == "importlib.abc.Traversable")
                .count(),
            1,
            "{source}"
        );
        assert!(
            found
                .iter()
                .any(|site| site.detail == "importlib.abc.Traversable"
                    && site.trojan_horse.is_none()),
            "{source}"
        );
    }
    for (source, detail) in [
        (
            "from pickle import HIGHEST_PROTOCOL\nx = HIGHEST_PROTOCOL\n",
            "pickle.HIGHEST_PROTOCOL",
        ),
        (
            "from dill import settings\nx = settings['recurse']\n",
            "dill.settings",
        ),
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert_eq!(
            found.iter().filter(|site| site.detail == detail).count(),
            1,
            "{source}"
        );
        assert!(
            found
                .iter()
                .any(|site| site.detail == detail && site.trojan_horse.is_none()),
            "{source}"
        );
    }
    for source in [
        "from importlib.abc import Traversable\nTraversable = other\nx = Traversable\n",
        "from importlib.abc import Traversable\nfrom elsewhere import *\nx = Traversable\n",
        "from importlib.abc import Traversable\nx = Traversable.__self__\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert!(found.len() >= 2, "{source}");
    }
}

#[test]
fn dill_settings_reads_keep_the_import_gap() {
    for source in [
        "import dill\nx = dill.settings['protocol']\n",
        "import dill as d\nx = d.settings['recurse']\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert!(
            found
                .iter()
                .any(|site| site.detail == "dill" && site.trojan_horse.is_none()),
            "{source}"
        );
        assert!(
            !found.iter().any(|site| site.detail == "dill.settings"),
            "{source}"
        );
    }
    for source in [
        "import dill\ndill.settings = replacement\n",
        "import dill\ndef f(dill): return dill.settings\n",
        "import dill\ndill = replacement\nx = dill.settings\n",
        "import dill\nfrom elsewhere import *\nx = dill.settings\n",
        "import dill\nx = dill.settings.other\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert!(
            found.iter().any(|site| site.detail == "dill.settings"),
            "{source}"
        );
    }
}

#[test]
fn trojan_horse_strings_with_unproved_equality_or_membership_keep_their_gap() {
    for source in [
        "result = value == '__import__'\n",
        "result = value in {'__import__'}\n",
        "names = {'__import__'}\nresult = value in names\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert!(
            found.iter().any(|site| site.detail == "__import__"),
            "{source}"
        );
    }
}

/// AD-1048: a code object that a function hands out is a door; a scalar field of it is a read.
#[test]
fn a_code_object_is_a_door_and_a_scalar_field_of_it_is_not() {
    let kinds = |source: &str| -> Vec<&'static str> {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        )
        .iter()
        .map(|site| site.kind)
        .collect()
    };
    for source in [
        "def f(): pass\nf.__code__ = f.__code__.replace(co_names=())\n",
        "def f(): pass\nc = f.__code__\n",
        "def f(): pass\nx = f.__code__.replace(co_names=())\n",
        "def f(): pass\nx = f.__code__.co_consts\n",
        "def f(): pass\nx = f.__code__.co_names\n",
        "import sys\nx = sys._getframe().f_code\n",
        "def g():\n    yield 1\nx = g().gi_code\n",
        "def f(): pass\nsetattr(f, '__code__', other)\n",
        "def f(): pass\nx = getattr(f, '__code__')\n",
    ] {
        assert!(kinds(source).contains(&DYNAMIC), "{source}");
    }
    for source in [
        "def f(): pass\nx = f.__code__.co_name\n",
        "def f(): pass\nx = f.__code__.co_filename\n",
        "def f(): pass\nx = f.__name__\n",
        "def f(): pass\nx = f.__defaults__\n",
    ] {
        assert!(kinds(source).is_empty(), "{source}");
    }
}

/// The `detail` of each site of the source.
fn clear_details(source: &str) -> Vec<String> {
    let tree = crate::test_tree(source, 14).expect("valid probe");
    let binders = vec![Binders::of(&tree)];
    let name = ("app/x.py".to_owned(), "app.x".to_owned());
    let module = Module::new(name.0, name.1, source.to_owned(), tree);
    let (_, found) = split(&[module], &binders, (None, false), false);
    found.into_iter().map(|(_, site)| site.detail).collect()
}

fn clear_count(source: &str, detail: &str) -> usize {
    let under = format!("{detail}.");
    let found = clear_details(source);
    found
        .iter()
        .filter(|found| *found == detail || found.starts_with(&under))
        .count()
}

#[test]
fn a_code_type_in_an_annotation_is_no_site_and_each_other_use_is() {
    let import = "from types import CodeType\n";
    // AD-1058: only the annotation of a local variable is neither evaluated nor stored.
    for body in [
        "def f():\n    c: CodeType | None = None\n",
        "def f():\n    x: list[CodeType] = []\n    y: tuple[CodeType, int]\n",
    ] {
        let source = format!("{import}{body}");
        assert_eq!(clear_count(&source, "types.CodeType"), 1, "{source}");
    }
    // Each other annotation is stored in `__annotations__`, where code can read the class back
    // and call it (`H.__annotations__['code'](...)`): it keeps its site.
    for body in [
        "def f(c: CodeType) -> CodeType | None:\n    return None\n",
        "def f(*a: CodeType, **k: CodeType): ...\n",
        "x: CodeType | None = None\n",
        "class A:\n    code: CodeType\n    def m(self, c: Optional[CodeType]): ...\n",
        "def f():\n    class A:\n        code: CodeType\n",
    ] {
        let source = format!("{import}{body}");
        assert!(clear_count(&source, "types.CodeType") >= 2, "{source}");
    }
    for body in [
        "def f(c=CodeType): ...\n",
        "x = CodeType\n",
        "CodeType(1, 2)\n",
        "def f(c: Annotated[int, CodeType(1)]): ...\n",
        "def f(c: Annotated[int, CodeType.replace]): ...\n",
        "class A(CodeType): ...\n",
        "def f():\n    return CodeType\n",
    ] {
        let source = format!("{import}{body}");
        assert!(clear_count(&source, "types.CodeType") >= 2, "{source}");
    }
    // The attribute form clears in a local annotation and in the class test of `isinstance`.
    for source in [
        "import types\ndef f():\n    c: types.CodeType\n    d: types.FunctionType = None\n",
        "import types as t\ndef f():\n    c: t.CodeType | None = None\n",
        "import types\nok = isinstance(x, types.CodeType)\n",
    ] {
        assert!(clear_details(source).is_empty(), "{source}");
    }
    for source in [
        "import types\ndef f(c: types.CodeType): ...\n",
        "import types\nx: types.FunctionType = None\n",
        "import types\nclass H:\n    code: types.CodeType\n",
    ] {
        assert!(!clear_details(source).is_empty(), "{source}");
    }
    // A use of the class, a rebound module name and a rebound name are no proven class.
    for source in [
        "import types\nx = types.CodeType\n",
        "import types\nx = types.CodeType(1)\n",
        "import types\nok = isinstance(types.CodeType, x)\n",
        "import types\nok = isinstance(x, types.CodeType, y)\n",
        "import types\ndef isinstance(a, b): ...\nok = isinstance(x, types.CodeType)\n",
        "import types\nimport other as types\ndef f(c: types.CodeType): ...\n",
        "def f(types, c: types.CodeType): ...\n",
        "from types import CodeType\nfrom other import CodeType\ndef f(c: CodeType): ...\n",
    ] {
        let found = clear_details(source);
        let class = found.iter().any(|item| item.starts_with("types."));
        assert!(
            class || source.contains("def f(types"),
            "{source}: {found:?}"
        );
    }
}

#[test]
fn a_literal_membership_test_of_sys_modules_is_no_site() {
    for source in [
        "import sys\nif 'numpy' in sys.modules:\n    pass\n",
        "import sys\nok = 'numpy' not in sys.modules\n",
        "import sys as s\nok = 'numpy' in s.modules\n",
    ] {
        assert_eq!(clear_count(source, "sys.modules"), 0, "{source}");
    }
    for source in [
        "import sys\nx = sys.modules['numpy']\n",
        "import sys\nx = sys.modules.get('numpy')\n",
        "import sys\nm = sys.modules\nok = 'numpy' in m\n",
        "import sys\nok = name in sys.modules\n",
        "import sys\nok = 'a' in sys.modules in other\n",
        "import sys\nok = 'a' in sys.modules.keys()\n",
        "import sys\nok = 'a' in sys.modules\nsys.modules['b'] = c\n",
        "from sys import modules\nok = 'a' in modules\n",
        "ok = 'a' in sys.modules\n",
        "import sys\nimport sys\nok = 'a' in sys.modules\n",
    ] {
        assert!(clear_count(source, "sys.modules") >= 1, "{source}");
    }
}

#[test]
fn only_the_key_view_of_globals_in_a_pure_builtin_is_no_site() {
    for source in [
        "x = sorted(set(globals().keys()))\n",
        "def f():\n    return len(globals().keys())\n",
        "x = list(globals().keys())\n",
    ] {
        assert_eq!(clear_count(source, "globals"), 0, "{source}");
    }
    for source in [
        "x = globals()[k]\n",
        "x = globals().items()\n",
        "x = globals().values()\n",
        "x = list(globals())\n",
        "x = g(globals().keys())\n",
        "x = globals().keys()\n",
        "for k in globals().keys():\n    pass\n",
        "x = set(globals().keys(), 1)\n",
        "def set(v):\n    return v\nx = set(globals().keys())\n",
        "x = set(globals(1).keys())\n",
        "x = set(globals().keys(1))\n",
        "g = globals\nx = set(g().keys())\n",
    ] {
        assert!(clear_count(source, "globals") >= 1, "{source}");
    }
}

const SPEC_HEAD: &str = "import pkgutil\ndef f(package):\n    s = package.__spec__\n";

#[test]
fn a_spec_that_is_only_tested_and_read_for_names_is_no_site() {
    for tail in [
        "    if s is None or s.submodule_search_locations is None:\n        return\n",
        "    name = s.name + s.parent\n",
        "    return list(pkgutil.walk_packages(s.submodule_search_locations, s.name + '.'))\n",
        "    return len(s.submodule_search_locations)\n",
        "    if None is not s:\n        return 1\n",
    ] {
        let source = format!("{SPEC_HEAD}{tail}");
        assert_eq!(clear_count(&source, "__spec__"), 0, "{source}");
    }
    for tail in [
        "    return s\n",
        "    g(s)\n",
        "    x = s\n",
        "    return s.loader\n",
        "    s.loader.load_module('app.lib')\n",
        "    g(s.submodule_search_locations)\n",
        "    s.submodule_search_locations.append(p)\n",
        "    for p in s.submodule_search_locations:\n        pass\n",
        "    return s.name, s\n",
        "    s = other\n",
        "    return getattr(s, 'loader')\n",
        "    return s.origin\n",
        "    return lambda: s\n",
        "    global s\n    return s.name\n",
    ] {
        let source = format!("{SPEC_HEAD}{tail}");
        assert_eq!(clear_count(&source, "__spec__"), 1, "{source}");
    }
    // The value is not a plain name, or the holder is not a local of a function, or the callee
    // is not a pure reader.
    for source in [
        "def f():\n    s = load().__spec__\n    return s.name\n",
        "s = package.__spec__\nx = s.name\n",
        "import pkgutil as q\ndef f(p):\n    s = p.__spec__\n    return q.other(s.submodule_search_locations)\n",
        "def f(p):\n    s = p.__spec__\n    return g(s.submodule_search_locations)\n",
    ] {
        assert_eq!(clear_count(source, "__spec__"), 1, "{source}");
    }
    let control = "def f(p):\n    s = p.__spec__\n    return list(s.submodule_search_locations)\n";
    assert_eq!(clear_count(control, "__spec__"), 0);
}
