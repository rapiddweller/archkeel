// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;
use crate::parse::parse;
use ruff_python_ast::Stmt;

fn facts(text: &str) -> Binders {
    Binders::of(&parse(text, crate::test_minor(13)).expect("valid source"))
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

/// `names_typing_any` of the annotation `x: <expr>` that follows `prelude`.
fn proves(prelude: &str, expr: &str) -> bool {
    let tree = parse(&format!("{prelude}\nx: {expr}\n"), crate::test_minor(13)).expect("source");
    matches!(tree.body.last(), Some(Stmt::AnnAssign(last))
        if Binders::of(&tree).names_typing_any(&last.annotation))
}

#[test]
fn any_is_proven_only_when_every_binder_is_a_typing_import() {
    assert!(proves("from typing import Any", "Any"));
    assert!(proves("from typing_extensions import Any", "Any"));
    assert!(proves("if x:\n    from typing import Any", "Any"));
    assert!(proves("from typing import *", "Any"));
    assert!(proves(
        "from typing import *\nfrom typing import Any",
        "Any"
    ));
}

#[test]
fn any_is_not_proven_when_a_binder_or_a_star_import_may_be_something_else() {
    assert!(!proves("", "Any"));
    assert!(!proves("class Any: pass", "Any"));
    assert!(!proves("Any = object", "Any"));
    assert!(!proves("from typing import Any\nclass Any: pass", "Any"));
    assert!(!proves(
        "from typing import Any as A\nclass Any: pass",
        "Any"
    ));
    assert!(!proves("from m import Any", "Any"));
    assert!(!proves("from m import *", "Any"));
    assert!(!proves("from typing import *\nclass Any: pass", "Any"));
    assert!(!proves("class Any: pass\nfrom typing import *", "Any"));
    assert!(!proves("from typing import *\nfrom m import *", "Any"));
}

#[test]
fn an_attribute_any_is_proven_only_for_a_name_of_the_typing_module() {
    assert!(proves("import typing", "typing.Any"));
    assert!(proves("import typing as t", "t.Any"));
    assert!(proves("import typing_extensions as te", "te.Any"));
    assert!(proves("if x:\n    import typing", "typing.Any"));
    assert!(!proves("import typing\ntyping = 1", "typing.Any"));
    assert!(!proves("import typing.io", "typing.Any"));
    assert!(!proves("import mylib", "mylib.Any"));
    assert!(!proves("class Outer:\n    class Any: pass", "Outer.Any"));
    assert!(!proves("import typing\nfrom m import *", "typing.Any"));
    assert!(!proves("import typing", "typing.sub.Any"));
}
