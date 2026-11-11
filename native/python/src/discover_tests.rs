// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_snapshot::test_tree::Tree;

use super::*;

#[test]
fn the_walk_selects_python_files_in_the_order_of_their_parts() {
    let tree = Tree::new(&[
        ("src/a.b/c.py", ""),
        ("src/a/b.py", ""),
        ("src/.hidden/e.py", ""),
        ("src/__pycache__/f.py", ""),
        ("src/Up.PY", ""),
        ("src/tests/test_x.py", ""),
        ("other/o.py", ""),
    ]);
    let mut snapshot = Snapshot::new(&tree.path());
    let roots = ["src".to_owned()];
    let all = selected(&mut snapshot, &roots, false);
    assert_eq!(
        all,
        [
            "src/.hidden/e.py",
            "src/a/b.py",
            "src/a.b/c.py",
            "src/tests/test_x.py"
        ]
    );
    assert!(!selected(&mut snapshot, &roots, true).contains(&"src/tests/test_x.py".to_owned()));
}

#[test]
fn a_test_source_is_named_by_a_directory_or_by_the_file_name() {
    assert!(is_test_source("pkg/tests/helpers.py"));
    assert!(is_test_source("pkg/test_api.py"));
    assert!(is_test_source("pkg/api_test.py"));
    assert!(!is_test_source("tests"));
    assert!(!is_test_source("pkg/testing.py"));
    assert!(!is_test_source("pkg/contest.py"));
}
