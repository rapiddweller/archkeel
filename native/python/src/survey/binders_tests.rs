// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::parse::parse;

fn facts(text: &str) -> Binders {
    Binders::of(&parse(text, 13).expect("valid source"))
}

fn unique(text: &str) -> Vec<String> {
    let mut names: Vec<String> = facts(text).unique().into_iter().collect();
    names.sort();
    names
}

#[test]
fn a_name_bound_once_at_the_top_is_unique() {
    let text = "import os\nimport a.b\nfrom x import y as z\ndef f(p): pass\nclass C: pass\n";
    assert_eq!(unique(text), ["C", "a", "f", "os", "z"]);
}

#[test]
fn a_second_binder_anywhere_removes_the_name() {
    assert_eq!(unique("import os\ndef g():\n    os = 1\n"), ["g"]);
    assert_eq!(unique("def f(): pass\nlambda f: f\n"), Vec::<String>::new());
    assert_eq!(
        unique("import os\ntry:\n    pass\nexcept E as os:\n    pass\n"),
        Vec::<String>::new()
    );
    assert_eq!(unique("import os\ndef g():\n    global os\n"), ["g"]);
    assert_eq!(
        unique("import os\nmatch v:\n    case [*os]: pass\n"),
        Vec::<String>::new()
    );
    assert_eq!(
        unique("import os\nmatch v:\n    case {**os}: pass\n"),
        Vec::<String>::new()
    );
    assert_eq!(unique("import os\ndel os\n"), Vec::<String>::new());
}

#[test]
fn a_nested_definition_is_not_direct() {
    assert_eq!(unique("if x:\n    def f(): pass\n"), Vec::<String>::new());
    assert_eq!(unique("if x:\n    import os\n"), Vec::<String>::new());
}

#[test]
fn a_star_import_or_a_type_parameter_empties_the_set() {
    assert_eq!(unique("import os\nfrom m import *\n"), Vec::<String>::new());
    assert_eq!(
        unique("import os\ndef f[T](): pass\n"),
        Vec::<String>::new()
    );
}

#[test]
fn the_literal_all_reads_every_top_level_literal() {
    let found = facts("__all__ = ['a', 'b']\n__all__ += ['c']\nx = __all__ = ('d', 1)\n");
    let mut exports: Vec<&String> = found.all_exports.iter().collect();
    exports.sort();
    assert_eq!(exports, ["a", "b", "d"]);
    assert!(!found.all_literal);
}

#[test]
fn the_all_is_one_literal_only_when_nothing_else_names_it() {
    assert!(facts("__all__ = ['a']\n").all_literal);
    assert!(facts("__all__: list = ('a',)\n").all_literal);
    assert!(facts("__all__ = __all__ = ['a']\n").all_literal);
    assert!(!facts("__all__ = ['a']\nprint(__all__)\n").all_literal);
    assert!(!facts("__all__ = ['a']\nfrom m import __all__\n").all_literal);
    assert!(!facts("__all__ = ['a', f'b']\n").all_literal);
    assert!(!facts("__all__ = {'a'}\n").all_literal);
}

#[test]
fn a_module_of_imports_and_one_literal_all_is_free_of_logic() {
    assert!(facts("'''doc'''\nimport os\n__all__ = ['os']\n").logic_free);
    assert!(!facts("import os\n").logic_free);
    assert!(!facts("__all__ = ['a']\nx = 1\n").logic_free);
    assert!(!facts("__all__ = ['a']\n__all__ = ['b']\n").logic_free);
    assert!(!facts("").logic_free);
}
