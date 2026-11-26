// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the kind of a class with a base of another module (#2129). The plants that run under
// CPython and the core are in `tests/test_cli_python_class_kind_project.py`.

use archkeel_facts::{FactData, SymbolFact};

use super::*;
use crate::module::Module;

fn module(name: &str, text: &str) -> Module {
    let path = format!("{}.py", name.replace('.', "/"));
    Module::new(
        path,
        name.into(),
        text.into(),
        crate::test_tree(text, 12).expect("fixture parses"),
    )
}

/// The base targets of each class record of the module `name`, after a project pass over `files`.
fn targets(files: &[(&str, &str)], name: &str) -> Vec<(String, Vec<String>)> {
    let modules: Vec<Module> = files.iter().map(|(n, t)| module(n, t)).collect();
    let binders: Vec<Binders> = modules.iter().map(|m| Binders::of(&m.tree)).collect();
    let table = project(&modules, &binders, |_, _| true);
    let at = modules.iter().position(|m| m.name == name).unwrap();
    let escapes = escapes::all(&modules, &binders, &[]).remove(at);
    let found = records(
        &modules[at],
        &binders[at],
        escapes,
        None,
        (&mut EvidenceMap::new(), &table),
    );
    let mut all = Vec::new();
    for record in &found.records {
        if let SymbolFact::Class(data) = &record.data {
            let name = record
                .data
                .fields()
                .qualified_name
                .unwrap_or_default()
                .to_owned();
            let bases = data
                .base_declarations
                .iter()
                .flat_map(|base| base.targets.clone())
                .collect();
            all.push((name, bases));
        }
    }
    all.sort();
    all
}

const BASE: (&str, &str) = ("app.base", "class Base:\n    pass\n");
const DERIVED: (&str, &str) = (
    "app.derived",
    "from app.base import Base\n\n\nclass D(Base):\n    pass\n",
);

#[test]
fn a_base_of_another_module_gives_the_kind_and_names_its_definition() {
    let found = targets(&[BASE, DERIVED], "app.derived");
    assert_eq!(
        found,
        [("app.derived.D".to_owned(), vec!["app.base.Base".to_owned()])]
    );
}

#[test]
fn a_re_export_gives_the_module_that_defines_the_class() {
    let facade = ("app.facade", "from app.base import Base\n");
    let derived = (
        "app.derived",
        "from app.facade import Base\n\n\nclass D(Base):\n    pass\n",
    );
    let found = targets(&[BASE, facade, derived], "app.derived");
    assert_eq!(found[0].1, ["app.base.Base"]);
}

#[test]
fn a_chain_of_classes_across_three_modules_is_a_fixpoint() {
    let middle = (
        "app.middle",
        "from app.base import Base\n\n\nclass M(Base):\n    pass\n",
    );
    let derived = (
        "app.derived",
        "from app.middle import M\n\n\nclass D(M):\n    pass\n",
    );
    // The order of the modules does not matter: derived comes first here.
    let found = targets(&[derived, middle, BASE], "app.derived");
    assert_eq!(found[0].1, ["app.middle.M"]);
}

#[test]
fn a_name_that_two_statements_bind_in_the_facade_gives_no_kind() {
    let other = ("app.other", "class Other:\n    pass\n");
    let facade = (
        "app.facade",
        "from app.base import Base\nfrom app.other import Other\n\nBase = Other\n",
    );
    let derived = (
        "app.derived",
        "from app.facade import Base\n\n\nclass D(Base):\n    pass\n",
    );
    assert!(targets(&[BASE, other, facade, derived], "app.derived").is_empty());
}

#[test]
fn a_module_that_is_not_admitted_gives_no_kind() {
    let modules: Vec<Module> = [BASE, DERIVED].iter().map(|(n, t)| module(n, t)).collect();
    let binders: Vec<Binders> = modules.iter().map(|m| Binders::of(&m.tree)).collect();
    let table = project(&modules, &binders, |_, m| m.name != "app.base");
    assert!(table.class("app.base", "Base").is_none());
    assert!(project(&modules, &binders, |_, _| true)
        .class("app.base", "Base")
        .is_some());
}

#[test]
fn a_decorated_class_a_keyword_and_a_call_give_no_kind() {
    for text in [
        "def d(c):\n    return c\n\n\n@d\nclass Base:\n    pass\n",
        "class Meta(type):\n    pass\n\n\nclass Base(metaclass=Meta):\n    pass\n",
        "def make():\n    return type('B', (), {})\n\n\nBase = make()\n",
        "import sys\n\nif sys.argv:\n    class Base:\n        pass\nelse:\n    class Base(int):\n        pass\n",
    ] {
        assert!(targets(&[("app.base", text), DERIVED], "app.derived").is_empty(), "{text}");
    }
}

#[test]
fn an_enum_and_a_protocol_base_give_no_kind_and_abc_gives_a_plain_one() {
    let mixed = (
        "app.derived",
        "from enum import Enum\nfrom typing import Protocol\n\n\nclass D(Enum, Protocol):\n    pass\n",
    );
    assert!(targets(&[mixed], "app.derived").is_empty());
    let abc = (
        "app.abc_base",
        "from abc import ABC\n\n\nclass A(ABC):\n    pass\n",
    );
    assert_eq!(targets(&[abc], "app.abc_base")[0].1, ["abc.ABC"]);
}

#[test]
fn a_relative_import_and_a_computed_base_give_no_kind() {
    for text in [
        "from .base import Base\n\n\nclass D(Base):\n    pass\n",
        "import importlib\n\nBase = importlib.import_module('app.base').Base\n\n\nclass D(Base):\n    pass\n",
    ] {
        assert!(targets(&[BASE, ("app.derived", text)], "app.derived").is_empty(), "{text}");
    }
}
