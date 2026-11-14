// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: each site becomes a gap of the survey (AD-450). A missed site can hide an edge.

use super::*;

fn found(source: &str) -> Vec<(&'static str, String)> {
    let tree = crate::test_tree(source, 14).expect("valid probe");
    sites(&tree)
        .into_iter()
        .map(|site| (site.kind, site.detail))
        .collect()
}

#[test]
fn each_import_function_and_text_runner_is_a_dynamic_import() {
    for (source, name) in [
        ("importlib.import_module(name)\n", "import_module"),
        ("import_module(name)\n", "import_module"),
        ("__import__(name)\n", "__import__"),
        ("exec(text)\n", "exec"),
        ("eval(text)\n", "eval"),
        ("loader.load_module(name)\n", "load_module"),
        ("spec.loader.exec_module(module)\n", "exec_module"),
        (
            "importlib.util.module_from_spec(spec)\n",
            "module_from_spec",
        ),
        (
            "importlib.util.spec_from_file_location(n, p)\n",
            "spec_from_file_location",
        ),
        ("runpy.run_module(name)\n", "run_module"),
        ("runpy.run_path(path)\n", "run_path"),
        (
            "def later():\n    class Inner:\n        x = __import__(name)\n",
            "__import__",
        ),
    ] {
        assert_eq!(found(source), [(DYNAMIC, name.to_owned())], "{source}");
    }
}

#[test]
fn a_method_of_another_object_is_no_dynamic_import() {
    assert!(found("model.eval()\nself.exec()\n").is_empty());
}

#[test]
fn each_change_of_the_import_state_is_a_site() {
    for (source, name) in [
        ("sys.path.insert(0, 'x')\n", "sys.path.insert"),
        ("sys.path.append('x')\n", "sys.path.append"),
        ("sys.path = ['x']\n", "sys.path"),
        ("sys.path[0] = 'x'\n", "sys.path"),
        ("sys.path += ['x']\n", "sys.path"),
        ("sys.modules['x'] = module\n", "sys.modules"),
        ("del sys.modules['x']\n", "sys.modules"),
        ("sys.meta_path.append(finder)\n", "sys.meta_path.append"),
        ("sys.path_hooks.insert(0, hook)\n", "sys.path_hooks.insert"),
        ("sys.modules.update(table)\n", "sys.modules.update"),
        ("site.addsitedir('x')\n", "addsitedir"),
        ("__path__ = paths\n", "__path__"),
    ] {
        assert_eq!(
            found(source),
            [(IMPORT_SYSTEM, name.to_owned())],
            "{source}"
        );
    }
    let extended = found("__path__ = pkgutil.extend_path(__path__, __name__)\n");
    assert_eq!(extended.len(), 2, "{extended:?}");
}

#[test]
fn a_read_of_the_import_state_is_no_site() {
    assert!(found("x = sys.modules.get('x')\ny = 'x' in sys.path\nz = sys.path[0]\n").is_empty());
}
