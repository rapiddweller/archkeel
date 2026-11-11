// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_snapshot::test_tree::Tree;

use super::*;

fn selected(snapshot: &mut Snapshot, roots: &[String], exclude: bool) -> Vec<String> {
    scope(snapshot, roots, exclude).selected
}

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

#[cfg(unix)]
#[test]
fn a_dangling_link_is_selected_and_kept_as_unseen() {
    let tree = Tree::new(&[("src/a.py", "")]);
    let src = std::path::Path::new(&tree.path()).join("src");
    std::os::unix::fs::symlink("missing.py", src.join("dangling.py")).unwrap();
    std::os::unix::fs::symlink("missing", src.join("dangling_dir")).unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    let found = scope(&mut snapshot, &["src".to_owned()], false);
    assert_eq!(found.selected, ["src/a.py", "src/dangling.py"]);
    assert_eq!(
        found.unseen,
        [Unseen::Missing("src/dangling.py".to_owned())]
    );
    assert_eq!(found.unseen[0].reason(&snapshot), None);
}

#[test]
fn a_file_over_the_size_limit_is_unseen_with_its_reason() {
    let big = "#".repeat(usize::try_from(archkeel_snapshot::MAX_FILE_BYTES).unwrap() + 1);
    let tree = Tree::new(&[("src/big.py", big.as_str()), ("src/a.py", "")]);
    let mut snapshot = Snapshot::new(&tree.path());
    let found = scope(&mut snapshot, &["src".to_owned()], false);
    let (inputs, _) = crate::inputs::inputs(&mut snapshot, &found.selected);
    assert_eq!(inputs.len(), 1);
    let unseen = oversized(&snapshot, &found.selected);
    assert_eq!(unseen, [Unseen::Oversized("src/big.py".to_owned())]);
    let reason = unseen[0].reason(&snapshot).unwrap();
    assert!(reason.contains("src/big.py"), "{reason}");
}

#[cfg(target_os = "linux")]
#[test]
fn a_name_that_is_not_utf8_is_unseen_with_its_reason() {
    use std::os::unix::ffi::OsStrExt;
    let tree = Tree::new(&[("src/a.py", "")]);
    let src = std::path::Path::new(&tree.path()).join("src");
    std::fs::write(src.join(std::ffi::OsStr::from_bytes(b"caf\xe9.py")), "").unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    let found = scope(&mut snapshot, &["src".to_owned()], false);
    assert_eq!(found.unseen.len(), 1);
    let reason = found.unseen[0].reason(&snapshot).unwrap();
    assert!(
        reason.starts_with("Source name is not UTF-8: src/caf"),
        "{reason}"
    );
}

#[cfg(unix)]
fn fifo(path: &std::path::Path) {
    let made = std::process::Command::new("mkfifo").arg(path).status();
    assert!(made.is_ok_and(|status| status.success()));
}

#[cfg(unix)]
#[test]
fn a_fifo_named_py_is_unseen_and_never_read() {
    let tree = Tree::new(&[("src/a.py", ""), ("src/__pycache__/c.py", "")]);
    let src = std::path::Path::new(&tree.path()).join("src");
    fifo(&src.join("pipe.py"));
    fifo(&src.join("__pycache__/pipe.py"));
    fifo(&src.join("test_pipe.py"));
    std::os::unix::fs::symlink("pipe.py", src.join("link.py")).unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    let found = scope(&mut snapshot, &["src".to_owned()], true);
    assert_eq!(found.selected, ["src/a.py"]);
    let expected = ["src/link.py", "src/pipe.py"].map(|rel| Unseen::Special(rel.to_owned()));
    assert_eq!(found.unseen, expected);
    let reason = found.unseen[1].reason(&snapshot).unwrap();
    assert_eq!(reason, "Source is not a regular file: src/pipe.py");
    let all = scope(&mut snapshot, &["src".to_owned()], false);
    assert_eq!(all.unseen.len(), 3);
}

#[cfg(unix)]
#[test]
fn a_dangling_link_under_pycache_is_not_selected() {
    let tree = Tree::new(&[("src/__pycache__/c.py", "")]);
    let cache = std::path::Path::new(&tree.path()).join("src/__pycache__");
    std::os::unix::fs::symlink("missing.py", cache.join("dangling.py")).unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    let found = scope(&mut snapshot, &["src".to_owned()], false);
    assert!(found.selected.is_empty());
    assert!(found.unseen.is_empty());
}

#[cfg(unix)]
#[test]
fn a_link_to_a_test_source_is_a_test_source() {
    let tree = Tree::new(&[("src/real/test_a.py", "")]);
    let src = std::path::Path::new(&tree.path()).join("src");
    std::os::unix::fs::symlink("real/test_a.py", src.join("alias.py")).unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    let roots = ["src".to_owned()];
    assert!(selected(&mut snapshot, &roots, true).is_empty());
    assert_eq!(
        selected(&mut snapshot, &roots, false),
        ["src/alias.py", "src/real/test_a.py"]
    );
}
