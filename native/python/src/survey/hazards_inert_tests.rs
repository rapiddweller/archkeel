// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Inert-read and retained-door plants for the Python import survey.

use super::*;

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
        assert!(matching[0].door.is_none(), "{source}");
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
                .any(|site| site.detail == "importlib.metadata" && site.door.is_none()),
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
                .any(|site| site.detail == "importlib.abc.Traversable" && site.door.is_none()),
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
                .any(|site| site.detail == detail && site.door.is_none()),
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
                .any(|site| site.detail == "dill" && site.door.is_none()),
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
fn door_strings_with_unproved_equality_or_membership_keep_their_gap() {
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
