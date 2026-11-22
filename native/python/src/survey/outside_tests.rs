// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a route through a module that code of the repository outside the scan writes is never
// proven (#1522, AD-770). The survey names such a module as an escaped one, as it names a module
// that a module of the scan writes (AD-504).

use crate::survey::targets::tests::surveyed;

/// The escaped modules, with the files outside the scan roots `outside`.
fn escaped(outside: &[(&str, &str)]) -> Vec<String> {
    let mut files = vec![
        ("src/app/__init__.py", ""),
        ("src/app/lib/__init__.py", "from app.lib.pub import f\n"),
        ("src/app/lib/pub.py", "def f(): return 1\n"),
        ("src/app/lib/_priv.py", "def secret(): return 2\n"),
        ("src/app/consumer.py", "from app.lib import f\n"),
    ];
    files.extend_from_slice(outside);
    let mut names: Vec<String> = surveyed(&files).opaque_surface.into_iter().collect();
    names.sort();
    names
}

const WRITE: &str = "from app.lib._priv import secret\nimport app.lib\napp.lib.f = secret\n";

const HOOK: &str = "import app.lib\napp.lib.__dict__['f'] = None\n";
const SETATTR: &str = "from app import lib\nsetattr(lib, 'f', None)\n";
const READ: &str = "import app.lib\nprint(app.lib.f())\nfrom app.lib import f\nf()\n";
const TAG: &str = "Signature: 8a477f597d28d172789f06886806bc55\n";
const LOAD: &str = "import importlib\ndef load(n): return importlib.import_module(n)\n";

#[test]
fn a_script_outside_the_roots_that_writes_a_module_escapes_it() {
    for (rel, text) in [
        ("outside.py", WRITE),
        ("scripts/patch.py", SETATTR),
        ("tools/run.pyw", "import app.lib as m\nm.f = None\n"),
        ("bin/hook.py", HOOK),
    ] {
        let found = escaped(&[(rel, text)]);
        assert!(found.contains(&"app.lib".to_owned()), "{rel}: {text}");
    }
}

#[test]
fn a_trojan_horse_in_a_script_escapes_the_modules_that_its_strings_name() {
    for text in [
        "import importlib\nimportlib.import_module('app.lib').f = None\n",
        "import sys\nsys.modules['app.lib'].f = None\n",
        &format!("{LOAD}load('app.lib').f = 1\n"),
    ] {
        let found = escaped(&[("outside.py", text)]);
        assert!(found.contains(&"app.lib".to_owned()), "{text}");
    }
}

#[test]
fn code_that_writes_no_module_of_the_scan_changes_nothing() {
    let base = escaped(&[]);
    let cases: [&[(&str, &str)]; 11] = [
        // A read, a call and a named import are no write (AD-504).
        &[("outside.py", READ)],
        &[("outside.py", "from app.lib.pub import f\nf()\n")],
        // A test file is under the stated premise of the run, not read.
        &[("tests/test_patch.py", WRITE)],
        &[("patch_test.py", WRITE)],
        // Build output and installed packages are not read.
        &[("build/CACHEDIR.TAG", TAG), ("build/lib/patch.py", WRITE)],
        &[
            (".venv/pyvenv.cfg", "home = /usr\n"),
            (".venv/lib/patch.py", WRITE),
        ],
        // A file that Python cannot run writes nothing.
        &[("broken.py", "import app.lib\napp.lib.f = = 1\n")],
        // A trojan horse whose name cannot name a module of the scan, and inert literal code.
        &[(
            "tools/load.py",
            "import importlib\nimportlib.import_module(f'tools.{x}')\n",
        )],
        &[(
            "tools/pick.py",
            "import importlib\nimportlib.import_module('a' if c else 'b')\n",
        )],
        &[("tools/calc.py", "eval('1 + 1')\nexec('pass')\n")],
        // A trojan horse that spells no module of the scan: the premise covers the name.
        &[("tools/any.py", LOAD)],
    ];
    for files in cases {
        assert_eq!(escaped(files), base, "{files:?}");
    }
}

#[test]
fn an_extension_source_that_names_a_module_escapes_it_and_its_packages() {
    for (rel, text) in [
        ("vendor/patch.c", "PyImport_ImportModule(\"app.lib\");\n"),
        (
            "vendor/patch.c",
            "PyImport_ImportModule(\"app\" \".lib\");\n",
        ),
        ("vendor/patch.pyx", "from app.lib cimport f\n"),
        (
            "crates/ext/src/lib.rs",
            "use pyo3::prelude::*;\nfn f() { m(\"app.lib\"); }\n",
        ),
        ("vendor/patch.so", "\u{1}\u{2}app.lib\u{0}\u{3}"),
    ] {
        let found = escaped(&[(rel, text)]);
        for name in ["app", "app.lib", "app.lib._priv", "app.lib.pub"] {
            assert!(
                found.contains(&name.to_owned()),
                "{rel}: {name} in {found:?}"
            );
        }
    }
    let base = escaped(&[]);
    for (rel, text) in [
        ("crates/core/src/lib.rs", "fn f() { m(\"app.lib\"); }\n"),
        (
            "vendor/parser.c",
            "static const char *names[] = {\"other.lib\", \"apple\"};\n",
        ),
    ] {
        assert_eq!(escaped(&[(rel, text)]), base, "{rel}");
    }
}

const SPEC: &str = "import importlib.util\n\
    spec = importlib.util.spec_from_file_location({name}, 'other.py')\n\
    mod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\n";

fn loader(name: &str) -> String {
    SPEC.replace("{name}", name)
}

#[test]
fn a_loader_under_a_foreign_literal_name_writes_no_module_of_the_scan() {
    let base = escaped(&[]);
    let cases = [
        // The text that names the package is a string, not a name of a module of the object.
        format!(
            "PACKAGE = 'app'\nTOP = 'app.lib'\n{}",
            loader("'smoke_selection'")
        ),
        loader("name='smoke_selection'").replace("'other.py')", "'o.py')"),
        "from importlib.util import module_from_spec, spec_from_file_location\n\
         PACKAGE = 'app.lib'\nspec = spec_from_file_location('smoke', 'o.py')\n\
         module_from_spec(spec).run()\n"
            .to_owned(),
        "import importlib.util as u\nPACKAGE = 'app'\n\
         spec = u.spec_from_file_location('smoke', 'o.py')\nmod = u.module_from_spec(spec)\n\
         spec.loader.exec_module(mod)\nmod.SMOKE = 1\n"
            .to_owned(),
    ];
    for text in cases {
        assert_eq!(escaped(&[("script/select.py", &text)]), base, "{text}");
    }
}

#[test]
fn a_loader_that_can_name_a_module_of_the_scan_escapes_it() {
    let rest = "import importlib.util\nspec = importlib.util.spec_from_file_location";
    let cases = [
        // The spec name is a module of the scan, a package above one, a computed text.
        loader("'app.lib'"),
        loader("'app'"),
        loader("'app.lib._priv'"),
        loader("NAME") + "NAME = 'app.lib'\n",
        loader("f'app.{x}'") + "x = 'lib'\nTOP = 'app.lib'\n",
        loader("'.lib'") + "TOP = 'app.lib'\n",
        // One call with a foreign name does not clear a second call, an alias or a keyword path.
        format!("{rest}('smoke', 'o.py')\nspec = importlib.util.spec_from_file_location('app.lib', 'o.py')\n"),
        format!("{rest}('smoke', 'o.py')\nmake = importlib.util.spec_from_file_location\nTOP = 'app.lib'\n"),
        // A loader or a search path can run a file that the walk does not read.
        loader("'smoke'").replace("'other.py')", "'o.txt', loader=ld)") + "TOP = 'app.lib'\n",
        loader("'smoke'").replace("'other.py')", "'o.txt', ld)") + "TOP = 'app.lib'\n",
        // The state of the import system and a plain loader keep the strings of the file.
        loader("'smoke'") + "import sys\nsys.modules['app.lib'] = mod\n",
        loader("'smoke'") + "import importlib\nimportlib.import_module('app.lib')\n",
        loader("'smoke'") + "found = importlib.util.find_spec('app.lib')\n",
        // A loader whose spec name is no literal, with no foreign call at all.
        "import importlib.util\nspec = importlib.util.find_spec('app.lib')\n\
         mod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\n"
            .to_owned(),
        // A module object of the scan that the file passes on escapes it (AD-504).
        loader("'smoke'") + "import app.lib\nspec.loader.exec_module(app.lib)\n",
    ];
    for text in cases {
        let found = escaped(&[("script/select.py", &text)]);
        assert!(found.contains(&"app.lib".to_owned()), "{text}: {found:?}");
    }
}
