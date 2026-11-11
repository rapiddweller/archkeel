// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn a_module_starts_where_the_namespace_starts() {
    assert_eq!(
        module_for("src/app/x/y.py", "app", 12).as_deref(),
        Some("app.x.y")
    );
    assert_eq!(
        module_for("src/app/__init__.py", "app", 12).as_deref(),
        Some("app")
    );
    assert_eq!(
        module_for("a/app/b/app/c.py", "app.b", 12).as_deref(),
        Some("app.b.app.c")
    );
    assert_eq!(
        module_for("app/a.b.py", "app", 12).as_deref(),
        Some("app.a.b")
    );
    assert_eq!(module_for("other/x.py", "app", 12), None);
    assert_eq!(package_for("app.x.y"), "app.x");
    assert_eq!(package_for("app"), "app");
}

#[test]
fn a_package_wins_over_a_module_of_the_same_name() {
    let selected: Vec<String> = [
        "app/__init__.py",
        "app/fmt.py",
        "app/fmt/__init__.py",
        "app/x.py",
    ]
    .iter()
    .map(|rel| (*rel).to_owned())
    .collect();
    let found = shadowed(&selected, "app", 12);
    assert_eq!(found.len(), 1);
    assert_eq!(found[0].file, "app/fmt.py");
    assert_eq!(
        found[0].title(),
        "app/fmt.py: module is shadowed by a package of the same name"
    );
    assert!(found[0].id().starts_with("COVERAGE-"));
    assert_eq!(SHADOWED_KIND, "ShadowedModule");
    assert_eq!(
        found[0].message(),
        "module 'app.fmt' is shadowed by the package of the same name and is never imported"
    );
    // A namespace portion (a directory without `__init__.py`) does not shadow a module.
    let portion: Vec<String> = ["app/fmt.py", "app/fmt/a.py"]
        .iter()
        .map(|r| (*r).to_owned())
        .collect();
    assert!(shadowed(&portion, "app", 12).is_empty());
}

#[test]
fn the_repr_quotes_as_python_does() {
    assert_eq!(repr("a'b"), "\"a'b\"");
    assert_eq!(repr("a'b\""), "'a\\'b\"'");
    assert_eq!(repr("é\\"), "'é\\\\'");
}

#[test]
fn a_module_name_follows_the_suffix_rule_of_the_python_version() {
    for minor in [11, 12] {
        assert_eq!(
            module_for("src/app/..py", "app", minor).as_deref(),
            Some("app..")
        );
    }
    // 3.13 refuses the stem `.` with a `ValueError`, as a name outside the namespace.
    assert_eq!(module_for("src/app/..py", "app", 13), None);
    assert_eq!(
        module_for("src/app/...py", "app", 13).as_deref(),
        Some("app...")
    );
    // 3.14 splits as `os.path.splitext`: leading dots never start the suffix.
    assert_eq!(
        module_for("src/app/..py", "app", 14).as_deref(),
        Some("app...py")
    );
    assert_eq!(
        module_for("src/app/...py", "app", 14).as_deref(),
        Some("app....py")
    );
    assert_eq!(
        module_for("src/app/a..py", "app", 14).as_deref(),
        Some("app.a.")
    );
    assert_eq!(
        module_for("src/app/.h.py", "app", 14).as_deref(),
        Some("app..h")
    );
    assert_eq!(
        module_for("src/app/.py", "app", 14).as_deref(),
        Some("app..py")
    );
}

#[test]
fn the_repr_escapes_what_python_does_not_print() {
    let shadowed = Shadowed {
        file: "src/app/a.py".to_owned(),
        module: "app.a\u{a0}b\u{85}".to_owned(),
    };
    let message = shadowed.message();
    assert!(message.contains("'app.a\\xa0b\\x85'"), "{message}");
}
