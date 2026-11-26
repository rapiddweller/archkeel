// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the walk of the collector. `archkeel-snapshot` owns the reads, the containment and the
// limits, and tests them; these tests cover what is specific to Rust and the failure of a link.

use archkeel_snapshot::test_tree::Tree;

use super::*;

#[test]
fn invalid_utf8_names_the_file_instead_of_replacing_bytes() {
    let root = Tree::new(&[("bad.rs", "")]);
    std::fs::write(root.root.join("bad.rs"), b"fn f() {} //\xff").unwrap();
    let mut snapshot = Snapshot::new(&root.path());
    assert_eq!(
        read_text(&mut snapshot, "bad.rs").unwrap_err(),
        "File is not valid UTF-8: bad.rs"
    );
}

#[test]
fn walks_sorted_files_and_skips_the_build_output_and_hidden_directories() {
    let root = Tree::new(&[
        ("Cargo.toml", ""),
        ("b.rs", ""),
        ("a/x.rs", ""),
        ("target/t.rs", ""),
        (".hidden/h.rs", ""),
        ("a/y.txt", ""),
    ]);
    let mut snapshot = Snapshot::new(&root.path());
    assert_eq!(
        walk(&mut snapshot, "").0,
        ["Cargo.toml", "a/x.rs", "a/y.txt", "b.rs"]
    );
    assert_eq!(walk(&mut snapshot, "a").0, ["a/x.rs", "a/y.txt"]);
}

#[test]
fn a_module_directory_named_target_is_read_like_any_other() {
    let root = Tree::new(&[
        ("src/lib.rs", ""),
        ("src/target/mod.rs", ""),
        ("src/target/arm.rs", ""),
    ]);
    let mut snapshot = Snapshot::new(&root.path());
    assert_eq!(
        walk(&mut snapshot, "").0,
        ["src/lib.rs", "src/target/arm.rs", "src/target/mod.rs"]
    );
}

#[test]
fn a_directory_that_holds_a_cargo_marker_is_build_output_wherever_it_is() {
    let root = Tree::new(&[
        ("src/lib.rs", ""),
        ("out/CACHEDIR.TAG", ""),
        ("out/debug/x.rs", ""),
        ("build/.rustc_info.json", ""),
        ("build/y.rs", ""),
        ("src/target/CACHEDIR.TAG", ""),
        ("src/target/z.rs", ""),
    ]);
    let mut snapshot = Snapshot::new(&root.path());
    assert_eq!(walk(&mut snapshot, "").0, ["src/lib.rs"]);
}

#[test]
fn a_read_gives_the_text_and_a_failed_read_names_its_file() {
    let root = Tree::new(&[("a.rs", "fn a() {}")]);
    let mut snapshot = Snapshot::new(&root.path());
    assert_eq!(read_text(&mut snapshot, "a.rs").unwrap(), "fn a() {}");
    let reason = read_text(&mut snapshot, "none.rs").unwrap_err();
    assert!(reason.ends_with(": none.rs"), "{reason}");
}

#[test]
fn a_file_over_the_limit_gives_the_reason_of_the_snapshot_crate() {
    let root = Tree::new(&[("big.rs", "")]);
    let big = std::fs::File::options()
        .write(true)
        .open(root.root.join("big.rs"))
        .unwrap();
    big.set_len(archkeel_snapshot::MAX_FILE_BYTES + 1).unwrap();
    let mut snapshot = Snapshot::new(&root.path());
    let reason = read_text(&mut snapshot, "big.rs").unwrap_err();
    assert_eq!(reason, snapshot.size_gap("big.rs").unwrap());
    assert!(snapshot.inputs(|_, _, _| ()).is_empty());
}

#[cfg(unix)]
#[test]
fn a_link_that_stays_inside_is_followed_and_a_path_that_leaves_the_snapshot_is_not_read() {
    let outside = Tree::new(&[("secret.rs", "SECRET first line")]);
    let root = Tree::new(&[("real.rs", "x"), ("dir/in.rs", "y")]);
    let link = |from: std::path::PathBuf, to: &str| {
        std::os::unix::fs::symlink(from, root.root.join(to)).unwrap();
    };
    link(root.root.join("real.rs"), "inside.rs");
    link(outside.root.join("secret.rs"), "leak.rs");
    link(outside.root.clone(), "linkdir");
    let mut snapshot = Snapshot::new(&root.path());
    assert_eq!(read_text(&mut snapshot, "inside.rs").unwrap(), "x");
    for rel in ["leak.rs", "linkdir/secret.rs"] {
        assert!(read_text(&mut snapshot, rel).is_err(), "{rel}");
        assert!(!snapshot.is_file(rel));
    }
    assert!(!snapshot.is_dir("linkdir"));
    let listed = walk(&mut snapshot, "").0;
    assert_eq!(listed, ["dir/in.rs", "inside.rs", "real.rs"]);
    assert!(snapshot
        .inputs(|path, _, _| path.contains("secret"))
        .iter()
        .all(|found| !found));
    // The escape is a problem, and the collector turns each problem into a gap.
    assert!(!snapshot.problems.is_empty());
}

#[cfg(unix)]
#[test]
fn a_link_loop_inside_the_snapshot_is_walked_once() {
    let root = Tree::new(&[("a/x.rs", "")]);
    std::os::unix::fs::symlink(&root.root, root.root.join("a/up")).unwrap();
    let mut snapshot = Snapshot::new(&root.path());
    assert_eq!(walk(&mut snapshot, "").0, ["a/x.rs"]);
}

#[test]
fn a_directory_below_the_depth_limit_is_listed_as_not_entered() {
    let deep = vec!["d"; 130].join("/");
    let file = format!("{deep}/x.rs");
    let root = Tree::new(&[("a.rs", ""), (file.as_str(), "")]);
    let mut snapshot = Snapshot::new(&root.path());
    let (files, not_entered) = walk(&mut snapshot, "");
    assert_eq!(files, ["a.rs"]);
    assert_eq!(not_entered, [vec!["d"; 129].join("/")]);
}
