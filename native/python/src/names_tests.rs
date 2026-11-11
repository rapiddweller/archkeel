// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn a_module_starts_where_the_namespace_starts() {
    assert_eq!(
        module_for("src/app/x/y.py", "app").as_deref(),
        Some("app.x.y")
    );
    assert_eq!(
        module_for("src/app/__init__.py", "app").as_deref(),
        Some("app")
    );
    assert_eq!(
        module_for("a/app/b/app/c.py", "app.b").as_deref(),
        Some("app.b.app.c")
    );
    assert_eq!(module_for("app/a.b.py", "app").as_deref(), Some("app.a.b"));
    assert_eq!(module_for("other/x.py", "app"), None);
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
    let found = shadowed(&selected, "app");
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
    assert!(shadowed(&portion, "app").is_empty());
}

#[test]
fn the_repr_quotes_as_python_does() {
    assert_eq!(python_repr("a'b"), "\"a'b\"");
    assert_eq!(python_repr("a'b\""), "'a\\'b\"'");
    assert_eq!(python_repr("é\\"), "'é\\\\'");
}
