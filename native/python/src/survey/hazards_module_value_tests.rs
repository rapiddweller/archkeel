// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A read of a re-exported module name is keyed by its receiver (AD-1540, #2142). The read is a
//! site unless the receiver is provably no module: `self` of a proven class, a local that holds
//! one plain value, or a plain value. Each plant of the first list stays a site. CPython runs the
//! plants in `tests/test_collector_false_pass_python_module_attribute.py`.

use super::*;

const UTIL: &str = "import cProfile as cp\nvalue = 1\n";

/// The number of `module_value` sites in the last module; `app.util` holds a module that has a
/// hazard name, and the other modules are given as they are.
fn sites_of(consumer: &str, others: &[(&str, &str)]) -> usize {
    let mut all: Vec<(&str, &str)> = vec![("app.util", UTIL)];
    all.extend_from_slice(others);
    all.push(("app.k", consumer));
    let trees: Vec<_> = all
        .iter()
        .map(|(_, text)| crate::test_tree(text, 14).expect("valid probe"))
        .collect();
    let binders: Vec<_> = trees.iter().map(Binders::of).collect();
    let modules: Vec<_> = all
        .iter()
        .zip(trees)
        .map(|((name, text), tree)| {
            let rel = format!("{}.py", name.replace('.', "/"));
            Module::new(rel, (*name).to_owned(), (*text).to_owned(), tree)
        })
        .collect();
    let (_, found) = split(&modules, &binders, (None, false), false);
    let last = modules.len() - 1;
    found
        .into_iter()
        .filter(|(index, site)| *index == last && site.detail == "module_value")
        .count()
}

#[test]
fn a_read_on_a_receiver_that_can_be_a_module_is_a_site() {
    for source in [
        "from app import util\ndef f():\n    return util.cp\n",
        "def f(m):\n    return m.cp\n",
        "def f(g):\n    return g().cp\n",
        "def f(self):\n    return self.cp\n",
        "from lib import Base\nclass K(Base):\n    def f(self):\n        return self.cp\n",
        "import types\nclass K(types.ModuleType):\n    def f(self):\n        return self.cp\n",
        "class K:\n    def f(self):\n        self = other()\n        return self.cp\n",
        "class K:\n    def f(self):\n        for self in xs:\n            pass\n        return self.cp\n",
        "class K:\n    def f(self):\n        def g(self):\n            return self.cp\n        return g\n",
        "class K:\n    def f(self):\n        return lambda self: self.cp\n",
        "class K:\n    @staticmethod\n    def f(self):\n        return self.cp\n",
        "class K:\n    @other\n    def f(self):\n        return self.cp\n",
        "class K(metaclass=Meta):\n    def f(self):\n        return self.cp\n",
        "class K:\n    def __new__(cls):\n        return util\n    def f(self):\n        return self.cp\n",
        "@wrap\nclass K:\n    def f(self):\n        return self.cp\n",
        "class K:\n    def f(self):\n        return self.cp\nclass M(K, types.ModuleType): ...\n",
        "class K:\n    def f(self):\n        return self.cp\nclass K: ...\n",
        "def h():\n    class M(K, types.ModuleType): ...\nclass K:\n    def f(self):\n        return self.cp\n",
        "def f():\n    x = 'a'\n    x = util\n    return x.cp\n",
        "def f(m):\n    x = m\n    return x.cp\n",
        "def f():\n    x = g()\n    return x.cp\n",
        "class K: ...\nK = util\ndef f():\n    k = K()\n    return k.cp\n",
    ] {
        assert!(sites_of(source, &[]) >= 1, "{source}");
    }
}

#[test]
fn a_read_on_a_receiver_that_is_provably_no_module_is_no_site() {
    for source in [
        "class K:\n    def f(self):\n        return self.cp\n",
        "class B: ...\nclass K(B):\n    def f(self):\n        return self.cp\n",
        "from dataclasses import dataclass\n@dataclass\nclass K:\n    def f(self):\n        return self.cp\n",
        "class K(Exception):\n    def f(self):\n        return self.cp\n",
        "import enum\nclass K(enum.Enum):\n    def f(self):\n        return self.cp\n",
        "class K:\n    @property\n    def f(self):\n        return self.cp\n",
        "class K:\n    def f(self):\n        def g():\n            return self.cp\n        return g\n",
        "def f():\n    x = 'a'\n    return x.cp\n",
        "def f():\n    x = [1]\n    return x.cp\n",
        "class K: ...\ndef f():\n    k = K()\n    return k.cp\n",
        "class K: ...\ndef f():\n    return K().cp\n",
        "def f():\n    return 'a'.cp\n",
    ] {
        assert_eq!(sites_of(source, &[]), 0, "{source}");
    }
}

#[test]
fn a_class_of_another_module_is_proven_through_its_import() {
    let base = ("app.base", "class B:\n    pass\n");
    let proven = "from app.base import B\nclass K(B):\n    def f(self):\n        return self.cp\n";
    assert_eq!(sites_of(proven, &[base]), 0);
    let bad = (
        "app.base",
        "import types\nclass B(types.ModuleType):\n    pass\n",
    );
    assert_eq!(sites_of(proven, &[bad]), 1);
    let other = (
        "app.m",
        "from app.base import B\nimport types\nclass M(B, types.ModuleType): ...\n",
    );
    assert_eq!(sites_of(proven, &[base, other]), 1);
    let ctor = "from app.base import B\ndef f():\n    b = B()\n    return b.cp\n";
    assert_eq!(sites_of(ctor, &[base]), 0);
    assert_eq!(sites_of(ctor, &[bad]), 1);
}
