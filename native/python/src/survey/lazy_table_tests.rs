// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// A finite table can bound import calls. A missing edge can give a forbidden rule a false PASS.

use std::collections::BTreeSet;
use std::process::Command;

use archkeel_snapshot::test_tree::Tree;

use crate::survey::targets::tests::{reasons, surveyed, surveyed_at};

#[test]
fn lazy_table_imports_are_edges() {
    let init = r#"from importlib import import_module
T = {'first': (__spec__.parent, '.first'), 'second': (__spec__.parent, '.second')}
def __getattr__(name):
    value = T.get(name)
    if value is None:
        raise AttributeError(name)
    package, module = value
    if module == '__module__':
        result = import_module(f'.{name}', package=package)
        globals()[name] = result
        return result
    result = import_module(module, package=package)
    for key, (_, item_module) in T.items():
        if item_module == module:
            globals()[key] = getattr(result, key)
    return result
"#;
    let found = surveyed(&[
        ("src/app/__init__.py", init),
        ("src/app/first.py", "first = 1\n"),
        ("src/app/second.py", "second = 1\n"),
    ]);
    let targets: Vec<_> = found
        .imports
        .iter()
        .map(|item| item.data.data().target_module.as_str())
        .collect();
    assert!(targets.contains(&"app.first"), "{targets:?}");
    assert!(targets.contains(&"app.second"), "{targets:?}");
    assert!(
        reasons(&found).is_empty(),
        "{:?} {:?}",
        reasons(&found),
        found.unknowns
    );
}

#[test]
fn independently_read_entries_need_their_cartesian_product() {
    let init = r#"from importlib import import_module
T = {'a': ('app.a', '.one'), 'b': ('app.b', '.two')}
def __getattr__(name):
    value = T.get(name)
    if value is None:
        return None
    package, _ = value
    for key, (_, module) in T.items():
        if key == 'b':
            return import_module(module, package=package)
"#;
    let found = surveyed(&[
        ("src/app/__init__.py", init),
        ("src/app/a/__init__.py", ""),
        ("src/app/a/two.py", ""),
        ("src/app/b/__init__.py", ""),
        ("src/app/b/two.py", ""),
    ]);
    let targets: Vec<_> = found
        .imports
        .iter()
        .map(|item| item.data.data().target_module.as_str())
        .collect();
    assert!(targets.contains(&"app.a.two"), "{targets:?}");
}

#[test]
fn unsafe_neighbours_keep_a_gap() {
    let base = r#"from importlib import import_module
T = {'first': ('app', '.first')}
def __getattr__(name):
    value = T.get(name)
    if value is None:
        return None
    package, module = value
    return import_module(module, package=package)
"#;
    let cases = [
        base.replace(
            "def __getattr__",
            "T['first'] = ('app', '.other')\ndef __getattr__",
        ),
        base.replace(
            "def __getattr__",
            "T.update({'first': ('app', '.other')})\ndef __getattr__",
        ),
        base.replace("def __getattr__", "leak(T)\ndef __getattr__"),
        base.replace(
            "{'first': ('app', '.first')}",
            "dict(first=('app', '.first'))",
        ),
        base.replace("'first':", "key:"),
        base.replace("('app', '.first')", "('app', other)"),
        base.replace(
            "import_module(module, package=package)",
            "import_module(name, package=package)",
        ),
        base.replace(
            "value = T.get(name)",
            "import_module(name)\n    value = T.get(name)",
        ),
        base.replace(
            "return import_module(module, package=package)",
            "globals()['import_module'] = other\n    return import_module(module, package=package)",
        ),
        base.replace("'first':", "'import_module':"),
        base.replace("__getattr__", "lookup"),
        base.replace(
            "def __getattr__",
            "import sys\nsys.modules['app.first'] = object()\ndef __getattr__",
        ),
        base.replace("'app', '.first'", "__spec__.parent, '.first'")
            .replace("def __getattr__", "__spec__ = other\ndef __getattr__"),
    ];
    for source in cases {
        let found = surveyed(&[("src/app/__init__.py", &source), ("src/app/first.py", "")]);
        assert!(!reasons(&found).is_empty(), "{source}");
    }
}

#[test]
fn a_missing_module_under_a_namespace_package_keeps_a_gap() {
    let source = r#"from importlib import import_module
T = {'x': ('app', '.missing')}
def __getattr__(name):
    value = T.get(name)
    if value is None:
        return None
    package, module = value
    return import_module(module, package=package)
"#;
    let found = surveyed(&[("src/app/lazy.py", source)]);
    assert!(!reasons(&found).is_empty(), "{source}");
}

/// The modules of the project that Python imports when the module `app` is imported and the
/// names `requested` are read from it, or `None` without `python3.12`.
fn truth(tree: &Tree, requested: &[&str]) -> Option<BTreeSet<String>> {
    let script = "import sys\nsys.path[:0] = [sys.argv[1] + '/src', sys.argv[1]]\n\
        before = set(sys.modules)\nimport app\nfor n in sys.argv[2:]:\n    try:\n        getattr(app, n)\n    \
        except Exception:\n        pass\n\
        for m in sorted(sys.modules):\n    if m not in before and m.split('.')[0] in ('app', 'ext'):\n        print(m)\n";
    let root = tree.path();
    let done = Command::new("python3.12")
        .args(["-I", "-c", script, &root])
        .args(requested)
        .output()
        .ok()?;
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    let text = String::from_utf8(done.stdout).unwrap();
    Some(
        text.lines()
            .filter(|name| *name != "app")
            .map(str::to_owned)
            .collect(),
    )
}

const SHAPE: &str = r#"from importlib import import_module
from warnings import warn

_table = {
    'sub': (__spec__.parent, '__module__'),
    'Alpha': (__spec__.parent, '.first'),
    'Beta': (__spec__.parent, '.second'),
    'Gamma': ('ext', '.'),
    'Delta': ('ext', '.core'),
    'Old': (__spec__.parent, '.first'),
}
_old = {'Old'}


def _migrate(name):
    raise AttributeError(name)


def __getattr__(attr_name):
    if attr_name in _old:
        warn('old', stacklevel=2)
    entry = _table.get(attr_name)
    if entry is None:
        return _migrate(attr_name)
    package, module_name = entry
    if module_name == '__module__':
        result = import_module(f'.{attr_name}', package=package)
        globals()[attr_name] = result
        return result
    else:
        module = import_module(module_name, package=package)
        result = getattr(module, attr_name)
        g = globals()
        for k, (_, other) in _table.items():
            if other == module_name and k not in _old:
                g[k] = getattr(module, k)
        return result
"#;

fn shape_tree(init: &str) -> Tree {
    Tree::new(&[
        ("src/app/__init__.py", init),
        ("src/app/first.py", "Alpha = 1\nOld = 2\n"),
        ("src/app/second.py", "Beta = 1\n"),
        ("src/app/sub.py", "x = 1\n"),
        ("ext/__init__.py", "Gamma = 1\n"),
        ("ext/core.py", "Delta = 1\n"),
    ])
}

fn targets_of(found: &crate::survey::Survey) -> BTreeSet<String> {
    found
        .imports
        .iter()
        .map(|item| item.data.data().target_module.as_str().to_owned())
        .collect()
}

#[test]
fn the_shape_of_pydantic_has_no_gap_and_every_import_python_makes_is_an_edge() {
    let tree = shape_tree(SHAPE);
    let found = surveyed_at(&tree);
    assert!(reasons(&found).is_empty(), "{:?}", reasons(&found));
    let edges = targets_of(&found);
    for name in ["sub", "Alpha", "Beta", "Gamma", "Delta", "Old"] {
        let Some(truth) = truth(&tree, &[name]) else {
            return;
        };
        assert!(!truth.is_empty(), "{name}");
        assert!(
            truth.is_subset(&edges),
            "{name}: {truth:?} not in {edges:?}"
        );
    }
}

#[test]
fn a_package_of_one_entry_with_the_module_of_another_is_an_edge() {
    let init = SHAPE.replace("('ext', '.core')", "('ext', '.second')");
    let found = surveyed_at(&shape_tree(&init));
    assert!(targets_of(&found).contains("ext.second"));
    let found = surveyed_at(&shape_tree(
        &init.replace("'ext', '.second'", "'app', '.second'"),
    ));
    assert!(targets_of(&found).contains("app.second"));
}

#[test]
fn each_other_form_of_the_shape_keeps_a_gap() {
    let cases = [
        SHAPE.replace("def _migrate", "_table['x'] = ('app', '.first')\n\n\ndef _migrate"),
        SHAPE.replace("def _migrate", "_table.update({})\n\n\ndef _migrate"),
        SHAPE.replace("def _migrate", "_table = other()\n\n\ndef _migrate"),
        SHAPE.replace("'.second'", "name_of()"),
        SHAPE.replace("    entry = _table.get(attr_name)\n    if entry is None:\n        return _migrate(attr_name)\n",
            "    entry = _table.get(attr_name)\n    if entry is None:\n        pass\n"),
        SHAPE.replace("import_module(f'.{attr_name}'", "import_module(attr_name"),
        SHAPE.replace("'Old':", "'__path__':"),
        SHAPE.replace("def _migrate", "__spec__ = None\n\n\ndef _migrate"),
        SHAPE.replace("import_module(module_name, package=package)", "import_module(module_name + attr_name + attr_name, package=package)")
            .replace("'Old': (__spec__.parent, '.first'),", &(0..70)
                .map(|i| format!("'k{i}': ('app', '.m'),\n"))
                .collect::<String>()),
    ];
    for source in cases {
        let found = surveyed_at(&shape_tree(&source));
        assert!(!reasons(&found).is_empty(), "{source}");
    }
}

#[test]
fn another_module_that_names_the_table_keeps_a_gap() {
    let tree = Tree::new(&[
        ("src/app/__init__.py", SHAPE),
        ("src/app/first.py", ""),
        ("src/app/second.py", ""),
        (
            "src/app/sub.py",
            "from app import _table\n_table['Alpha'] = ('app', '.sub')\n",
        ),
        ("ext/__init__.py", ""),
        ("ext/core.py", ""),
    ]);
    assert!(!reasons(&surveyed_at(&tree)).is_empty());
}

fn star_tree(star_source: &str, other: &str) -> Tree {
    let star = "from .star import *\nfrom importlib import import_module";
    let init = SHAPE.replacen("from importlib import import_module", star, 1);
    Tree::new(&[
        ("src/app/__init__.py", &init),
        ("src/app/star.py", star_source),
        ("src/app/first.py", other),
        ("src/app/second.py", ""),
        ("src/app/sub.py", ""),
        ("ext/__init__.py", ""),
        ("ext/core.py", ""),
    ])
}

#[test]
fn a_star_import_of_a_literal_all_that_names_no_dependency_keeps_the_proof() {
    let found = surveyed_at(&star_tree("__all__ = ['one']\none = 1\n", ""));
    let gaps: Vec<_> = reasons(&found)
        .into_iter()
        .filter(|r| !r.starts_with("star_import"))
        .collect();
    assert!(gaps.is_empty(), "{gaps:?}");
    assert!(targets_of(&found).contains("app.first"));
}

#[test]
fn a_star_import_that_can_bind_a_dependency_keeps_the_gap() {
    for source in [
        "__all__ = ['import_module']\nfrom importlib import import_module\n",
        "__all__ = ['__spec__']\n__spec__ = None\n",
        "from importlib import import_module\n",
        "__all__ = ['one']\nother = 1\n__all__ += ['import_module']\n",
    ] {
        let found = surveyed_at(&star_tree(source, ""));
        let gaps: Vec<_> = reasons(&found)
            .into_iter()
            .filter(|r| r.starts_with("dynamic_import"))
            .collect();
        assert!(!gaps.is_empty(), "{source}");
    }
}

#[test]
fn a_literal_test_on_a_slot_leaves_out_the_impossible_candidates() {
    let found = surveyed_at(&shape_tree(SHAPE));
    let edges = targets_of(&found);
    for impossible in ["__module__", "ext.Alpha", "ext.sub", "app.Alpha"] {
        assert!(!edges.contains(impossible), "{impossible}: {edges:?}");
    }
    for possible in ["app.sub", "app.first", "ext", "ext.core"] {
        assert!(edges.contains(possible), "{possible}: {edges:?}");
    }
}
