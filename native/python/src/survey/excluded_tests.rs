// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn a_test_path_outside_the_namespace_is_named_under_its_source_root() {
    assert_eq!(
        module_name("src", "src/app/tests/a.py", "app", 12).as_deref(),
        Some("app.tests.a")
    );
    assert_eq!(
        module_name("src", "src/tests/__init__.py", "app", 12).as_deref(),
        Some("tests")
    );
    assert_eq!(
        module_name("src", "src/tests/.py", "app", 12).as_deref(),
        Some("tests..py")
    );
    assert_eq!(module_name("src", "lib/tests/a.py", "app", 12), None);
}

#[test]
fn an_excluded_package_matches_its_modules_and_not_a_longer_name() {
    let mut found = Excluded::default();
    found.prefixes.insert("app.tests".to_owned());
    found.modules.insert("app.test_x".to_owned());
    let names = |items: &[&str]| {
        items
            .iter()
            .map(|item| (*item).to_owned())
            .collect::<Vec<_>>()
    };
    assert!(found.matched(&names(&["app.tests.a"])).is_some());
    assert!(found.matched(&names(&["app.testsuite"])).is_none());
    assert_eq!(
        found
            .matched(&names(&["app", "app.test_x"]))
            .map(String::as_str),
        Some("app.test_x")
    );
}
