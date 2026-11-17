// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the `interface_boundary` rule judges each import record (AD-708). A use of a name
// through a module binding is the record of that name; a module object that escapes leaves the
// names of its import unread.

use archkeel_facts::ImportFact;

use crate::survey::targets::tests::surveyed;

/// The records of `app.user`: (target module, symbol, binding, symbols known).
fn records(user: &str) -> Vec<(String, Option<String>, Option<String>, bool)> {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        (
            "src/app/lib/__init__.py",
            "from app.lib import _priv\ndef f(): pass\n",
        ),
        ("src/app/lib/_priv.py", "def secret(): pass\n"),
        ("src/app/user.py", user),
    ]);
    let mut rows: Vec<_> = found
        .imports
        .iter()
        .filter_map(|record| match &record.data {
            ImportFact::Import(data) if data.source_module.as_str() == "app.user" => Some((
                data.target_module.as_str().to_owned(),
                data.symbol.clone(),
                data.binding.clone(),
                data.symbols_known,
            )),
            _ => None,
        })
        .collect();
    rows.sort();
    rows
}

fn row(
    target: &str,
    symbol: Option<&str>,
    binding: Option<&str>,
    known: bool,
) -> (String, Option<String>, Option<String>, bool) {
    (
        target.to_owned(),
        symbol.map(str::to_owned),
        binding.map(str::to_owned),
        known,
    )
}

#[test]
fn each_name_of_a_chain_through_a_module_binding_is_a_record() {
    assert_eq!(
        records("import app.lib\napp.lib._priv.secret()\n"),
        [
            row("app.lib", None, None, true),
            row("app.lib", None, Some("app"), true),
            row("app.lib._priv", None, None, true),
            row("app.lib._priv", Some("secret"), None, true),
        ]
    );
    assert_eq!(
        records("import app.lib as lib\nlib.f()\n"),
        [
            row("app.lib", None, Some("lib"), true),
            row("app.lib", Some("f"), None, true),
        ]
    );
}

#[test]
fn a_module_object_that_escapes_leaves_the_names_of_its_import_unread() {
    for user in [
        "import app.lib\nx = app.lib\n",
        "import app.lib as lib\nprint(lib)\n",
        "import app.lib as lib\nlib.__dict__\n",
        "import app.lib as lib\nlib.f = 1\n",
    ] {
        let found = records(user);
        let import = found.iter().find(|r| r.2.is_some()).unwrap();
        assert!(!import.3, "{user}: {found:?}");
    }
    let found = records("import app.lib as lib\nlib.f()\n");
    assert!(found.iter().all(|r| r.3), "{found:?}");
}
