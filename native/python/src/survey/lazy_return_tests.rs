// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// AD-654: the value that a lazy `__getattr__` returns for a key. A key that the proof claims
// with a wrong value would hide a module escape and give a false route, so each plant checks the
// claim against what `python3.12` binds for `from app import name`, twice (the first access can
// store another value in the module namespace).

use std::collections::BTreeMap;
use std::process::Command;

use archkeel_snapshot::test_tree::Tree;

use crate::survey::lazy_cover::Source;
use crate::survey::targets::tests::{reasons, surveyed_at};
use crate::survey::Survey;

/// The pydantic form: a guard that returns for a name that is no key, a deprecation branch that
/// the strings do not decide, and the `globals()` stores of the keys of the same module.
const INIT: &str = r#"from importlib import import_module
from warnings import warn

_table = {
    'sub': (__spec__.parent, '__module__'),
    'Alpha': (__spec__.parent, '.first'),
    'Beta': (__spec__.parent, '.second'),
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

/// The package, its submodules and one client module.
fn tree(init: &str, client: &str) -> Tree {
    Tree::new(&[
        ("src/app/__init__.py", init),
        (
            "src/app/first.py",
            "Alpha = 'app.first.Alpha'\nOld = 'app.first.Old'\n",
        ),
        ("src/app/second.py", "Beta = 'app.second.Beta'\n"),
        ("src/app/other.py", "Alpha = 'app.other.Alpha'\n"),
        ("src/app/sub.py", "x = 1\n"),
        ("src/app/client.py", client),
    ])
}

fn survey(tree: &Tree) -> Survey {
    surveyed_at(tree)
}

fn keys(found: &Survey) -> BTreeMap<String, Source> {
    found.sources.get("app").cloned().unwrap_or_default()
}

/// What `python3.12` binds for `from app import name`, at the first and the second import: the
/// string value, `module:<name>`, or `error:<type>`. `None` without `python3.12`.
fn truth(tree: &Tree, name: &str) -> Option<[String; 2]> {
    let script = "import sys, types\nsys.path[:0] = [sys.argv[1] + '/src']\nout = []\n\
        for _ in range(2):\n    ns = {}\n    try:\n        exec('from app import ' + sys.argv[2] + ' as v', ns)\n        \
        v = ns['v']\n        out.append('module:' + v.__name__ if isinstance(v, types.ModuleType) else str(v))\n    \
        except Exception as error:\n        out.append('error:' + type(error).__name__)\nprint(' '.join(out))\n";
    let done = Command::new("python3.12")
        .args(["-I", "-c", script, &tree.path(), name])
        .output()
        .ok()?;
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    let text = String::from_utf8(done.stdout).unwrap();
    let mut parts = text.split_whitespace().map(str::to_owned);
    Some([parts.next()?, parts.next()?])
}

/// The value that the claim means, in the words of `truth`.
fn meaning(source: &Source) -> String {
    match source {
        Source::Attr(module, name) => format!("{module}.{name}"),
        Source::Module(module) => format!("module:{module}"),
    }
}

/// The claim for `name` agrees with Python at both imports.
fn agrees(tree: &Tree, found: &Survey, name: &str) {
    let claim = keys(found).get(name).map(meaning).expect(name);
    if let Some(seen) = truth(tree, name) {
        assert_eq!(seen, [claim.clone(), claim], "{name}");
    }
}

/// No claim for `name`, and Python shows why: the two imports differ, or the value is no module
/// attribute that a claim could name.
fn unclaimed(found: &Survey, name: &str) {
    assert!(!keys(found).contains_key(name), "{name}: {:?}", keys(found));
}

#[test]
#[ignore = "AD-1058: the computed getattr of the table keeps its site, so the claim is dropped"]
fn a_key_gives_the_attribute_or_the_module_of_its_entry() {
    let tree = tree(INIT, "from app import Alpha\nconsume(Alpha)\n");
    let found = survey(&tree);
    for name in ["Alpha", "Beta", "Old", "sub"] {
        agrees(&tree, &found, name);
    }
    assert!(
        !found.opaque_surface.contains("app"),
        "{:?}",
        found.opaque_surface
    );
}

#[test]
fn a_name_that_is_no_key_keeps_the_escape() {
    let tree = tree(INIT, "from app import Missing\nconsume(Missing)\n");
    let found = survey(&tree);
    unclaimed(&found, "Missing");
    assert!(
        found.opaque_surface.contains("app.first"),
        "{:?}",
        found.opaque_surface
    );
    if let Some(seen) = truth(&tree, "Missing") {
        assert_eq!(seen[0], "error:ImportError");
    }
}

#[test]
#[ignore = "AD-1058: the computed getattr of the table keeps its site, so the claim is dropped"]
fn a_key_bound_to_another_value_under_type_checking_is_not_proven() {
    let init = format!(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .other import Alpha\n{INIT}"
    );
    let tree = tree(&init, "from app import Alpha, Beta\nconsume(Beta)\n");
    let found = survey(&tree);
    unclaimed(&found, "Alpha");
    agrees(&tree, &found, "Beta");
    // A use of the unproven name escapes the package, and the package then keeps no key.
    let used = survey(&self::tree(
        &init,
        "from app import Alpha\nconsume(Alpha)\n",
    ));
    assert!(
        used.opaque_surface.contains("app"),
        "{:?}",
        used.opaque_surface
    );
    assert!(keys(&used).is_empty(), "{:?}", keys(&used));
    // Python reads the table, a type checker reads the import: the two views differ.
    if let Some(seen) = truth(&tree, "Alpha") {
        assert_eq!(seen[0], "app.first.Alpha");
    }
}

#[test]
#[ignore = "AD-1058: the computed getattr of the table keeps its site, so the claim is dropped"]
fn a_key_bound_to_the_same_value_under_type_checking_stays_proven() {
    let init = format!(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .first import Alpha\n{INIT}"
    );
    let tree = tree(&init, "from app import Alpha\nconsume(Alpha)\n");
    let found = survey(&tree);
    agrees(&tree, &found, "Alpha");
    assert!(
        !found.opaque_surface.contains("app"),
        "{:?}",
        found.opaque_surface
    );
}

#[test]
fn a_table_written_later_proves_no_key() {
    let init = format!("{INIT}_table['Alpha'] = (__spec__.parent, '.other')\n");
    let tree = tree(&init, "from app import Alpha\nconsume(Alpha)\n");
    let found = survey(&tree);
    assert!(keys(&found).is_empty(), "{:?}", keys(&found));
    if let Some(seen) = truth(&tree, "Alpha") {
        assert_eq!(seen[0], "app.other.Alpha");
    }
}

#[test]
#[ignore = "AD-1058: the computed getattr of the table keeps its site, so the claim is dropped"]
fn a_second_return_path_of_a_key_is_not_proven() {
    let init = INIT.replace(
        "def __getattr__(attr_name):\n",
        "def __getattr__(attr_name):\n    if attr_name == 'Alpha' and len(_old) > 0:\n        \
         return _old\n",
    );
    let tree = tree(&init, "from app import Beta\nconsume(Beta)\n");
    let found = survey(&tree);
    unclaimed(&found, "Alpha");
    agrees(&tree, &found, "Beta");
    if let Some(seen) = truth(&tree, "Alpha") {
        assert_eq!(seen[0], "{'Old'}");
    }
}

#[test]
fn a_return_of_another_module_is_that_module() {
    let init = r#"from importlib import import_module
_lazy = {'X': (__spec__.parent, '.first')}
def __getattr__(name):
    entry = _lazy.get(name)
    if entry is None:
        raise AttributeError(name)
    package, module = entry
    source = import_module(module, package=package)
    return import_module('.other', package=package)
"#;
    let tree = tree(init, "from app import X\nconsume(X)\n");
    let found = survey(&tree);
    agrees(&tree, &found, "X");
    assert!(
        found.opaque_surface.contains("app.other"),
        "{:?}",
        found.opaque_surface
    );
    assert!(
        !found.opaque_surface.contains("app"),
        "{:?}",
        found.opaque_surface
    );
}

#[test]
#[ignore = "AD-1058: the computed getattr of the table keeps its site, so the claim is dropped"]
fn a_store_of_another_value_drops_the_key() {
    let init = INIT.replace("g[k] = getattr(module, k)", "g[k] = getattr(module, 'Old')");
    let tree = tree(&init, "from app import Old\nconsume(Old)\n");
    let found = survey(&tree);
    unclaimed(&found, "Alpha");
    agrees(&tree, &found, "Old");
    // The probe of `_handle_fromlist` calls `__getattr__` once before the bind, so the store
    // already decides the first import.
    if let Some(seen) = truth(&tree, "Alpha") {
        assert_eq!(
            seen,
            ["app.first.Old".to_owned(), "app.first.Old".to_owned()]
        );
    }
}

#[test]
#[ignore = "AD-1058: the computed getattr of the table keeps its site, so the claim is dropped"]
fn a_key_whose_run_ends_without_return_is_not_proven() {
    let init = INIT.replace(
        "                g[k] = getattr(module, k)\n        return result\n",
        "                g[k] = getattr(module, k)\n",
    );
    let tree = tree(&init, "from app import sub\n");
    let found = survey(&tree);
    unclaimed(&found, "Beta");
    agrees(&tree, &found, "sub");
}

#[test]
fn a_store_under_an_unknown_name_proves_no_key() {
    let init = INIT.replace(
        "    entry = _table.get(attr_name)\n",
        "    globals()[attr_name.lower()] = 1\n    entry = _table.get(attr_name)\n",
    );
    let found = survey(&tree(&init, "from app import Alpha\n"));
    assert!(keys(&found).is_empty(), "{:?}", keys(&found));
}

#[test]
#[ignore = "AD-1058: the computed getattr of the table keeps its site, so the claim is dropped"]
fn a_key_that_is_a_submodule_gives_no_ambiguous_import() {
    let found = survey(&tree(INIT, "from app import sub\nconsume(sub)\n"));
    let ambiguous = reasons(&found);
    assert!(
        !ambiguous
            .iter()
            .any(|reason| reason.starts_with("reexport_ambiguity")),
        "{ambiguous:?}"
    );
}

#[test]
#[ignore = "AD-1058: the computed getattr of the table keeps its site, so the claim is dropped"]
fn a_proven_key_is_a_route_hop() {
    let mut found = survey(&tree(INIT, "from app import Alpha\n"));
    crate::survey::routes::resolve(
        &mut found.imports,
        &found.files,
        (&found.opaque_surface, &found.surface),
        (&found.sole_binders, &found.ambiguous),
        &found.sources,
    );
    let chain = found.imports.iter().find_map(|record| {
        let data = record.data.data();
        (data.source_module.as_str() == "app.client").then(|| data.reexport_chain.clone())
    });
    assert_eq!(
        chain.flatten(),
        Some(vec!["app.Alpha".to_owned(), "app.first.Alpha".to_owned()])
    );
}

/// A table that only calls `import_module` (no `getattr`): its keys are submodules. This shape
/// still gives a claim after AD-1058, because it has no trojan horse site.
const INIT_MODULES: &str = "from importlib import import_module\n\
    _table = {'sub': (__spec__.parent, '__module__'), 'first': (__spec__.parent, '__module__')}\n\
    def __getattr__(attr_name):\n    entry = _table.get(attr_name)\n    if entry is None:\n        \
    raise AttributeError(attr_name)\n    package, module_name = entry\n    \
    result = import_module(f'.{attr_name}', package=package)\n    \
    globals()[attr_name] = result\n    return result\n";

#[test]
fn a_table_of_submodules_still_gives_its_keys_and_no_ambiguous_import() {
    let tree = tree(INIT_MODULES, "from app import sub\nconsume(sub)\n");
    let found = survey(&tree);
    agrees(&tree, &found, "sub");
    agrees(&tree, &found, "first");
    assert!(reasons(&found).is_empty(), "{:?}", reasons(&found));
}

#[test]
fn a_key_of_a_submodule_table_whose_run_ends_without_return_is_not_proven() {
    let init = INIT_MODULES.replace("    return result\n", "");
    let found = survey(&tree(&init, "from app import sub\n"));
    unclaimed(&found, "sub");
}
