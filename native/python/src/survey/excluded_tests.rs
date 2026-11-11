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

/// L-30: Python also judges the target of a dangling link (`resolve()` without a check), which the
/// native walk cannot read; each dangling link under the test exclusion is a named gap.
#[cfg(unix)]
#[test]
fn a_dangling_link_under_the_test_exclusion_is_a_gap_that_names_it() {
    use archkeel_snapshot::test_tree::Tree;
    let tree = Tree::new(&[
        ("src/app/__init__.py", ""),
        ("src/app/user.py", "import app.ghost\n"),
    ]);
    let app = std::path::Path::new(&tree.path()).join("src/app");
    std::os::unix::fs::symlink("ghost.py", app.join("test_link.py")).unwrap();
    std::os::unix::fs::symlink("tests/gone.py", app.join("helper.py")).unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    let found = Excluded::find(&mut snapshot, &["src".to_owned()], "app", 12);
    let gaps = found.gaps(&[], &HashMap::new(), false);
    let titles: Vec<&str> = gaps.iter().map(|gap| gap.title.as_str()).collect();
    assert_eq!(
        titles,
        [
            "Test exclusion cannot judge the dangling link src/app/helper.py",
            "Test exclusion cannot judge the dangling link src/app/test_link.py",
        ]
    );
    assert_eq!(gaps[0].subjects, ["src/app/helper.py"]);
}
