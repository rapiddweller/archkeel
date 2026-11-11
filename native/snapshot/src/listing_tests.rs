// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the Dart collector, which never follows a symbolic link and names each link as a
// gap. The walk must show a link as a link, and it must never read a file through a link, also a
// link that leaves the snapshot.

use std::fs;

use super::super::Snapshot;
use super::{Entry, RootCheck};
use crate::test_tree::Tree;

fn problems(snapshot: &Snapshot) -> Vec<&str> {
    snapshot.problems.iter().map(String::as_str).collect()
}

#[cfg(unix)]
#[test]
fn a_listing_shows_each_link_and_does_not_follow_it() {
    use std::os::unix::fs::symlink;

    let tree = Tree::new(&[("lib/a.dart", ""), ("lib/sub/b.dart", "")]);
    let lib = tree.root.join("lib");
    symlink(lib.join("a.dart"), lib.join("file_link.dart")).unwrap();
    symlink(lib.join("sub"), lib.join("dir_link")).unwrap();
    symlink(lib.join("missing"), lib.join("dangling.dart")).unwrap();
    symlink(std::env::temp_dir(), lib.join("outside")).unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    let listing = snapshot.listing("lib").unwrap();
    assert_eq!(
        listing,
        [
            ("a.dart".to_owned(), Entry::File),
            (
                "dangling.dart".to_owned(),
                Entry::Link {
                    to_directory: false
                }
            ),
            ("dir_link".to_owned(), Entry::Link { to_directory: true }),
            (
                "file_link.dart".to_owned(),
                Entry::Link {
                    to_directory: false
                }
            ),
            ("outside".to_owned(), Entry::Link { to_directory: true }),
            ("sub".to_owned(), Entry::Directory),
        ]
    );
    assert!(snapshot.is_link("lib/dir_link"));
    assert!(!snapshot.is_link("lib/sub"));
    assert!(!snapshot.is_link("lib/absent"));
    assert!(snapshot.problems.is_empty());
}

#[test]
fn a_missing_directory_has_no_listing_and_is_a_problem() {
    let tree = Tree::new(&[("lib/a.dart", "")]);
    let mut snapshot = Snapshot::new(&tree.path());
    assert_eq!(snapshot.listing("absent"), None);
    assert_eq!(problems(&snapshot), ["Unreadable source directory: absent"]);
}

#[test]
fn a_path_outside_the_snapshot_has_no_listing() {
    let tree = Tree::new(&[("lib/a.dart", "")]);
    let mut snapshot = Snapshot::new(&tree.path());
    assert_eq!(snapshot.listing("../x"), None);
    assert!(!snapshot.is_link("../x"));
    assert_eq!(snapshot.check_root("../x"), RootCheck::Escapes);
}

#[test]
fn a_walked_file_is_read_and_digested_once_its_root_is_checked() {
    let tree = Tree::new(&[
        ("lib/a.dart", "class A {}"),
        ("lib/src/b.dart", "b"),
        ("c.dart", "c"),
    ]);
    let mut snapshot = Snapshot::new(&tree.path());
    // Before the check of a root, no file is walked: the read refuses and names the file.
    assert_eq!(snapshot.read_walked("lib/a.dart"), None);
    assert_eq!(
        problems(&snapshot),
        ["Source outside a checked root: lib/a.dart"]
    );
    snapshot.problems.clear();
    assert_eq!(snapshot.check_root("lib"), RootCheck::Contained);
    snapshot.listing("lib").unwrap();
    assert_eq!(snapshot.read_walked("lib/a.dart").unwrap(), b"class A {}");
    // The listing of `lib` walks its real subdirectory `lib/src`.
    assert_eq!(snapshot.read_walked("lib/src/b.dart").unwrap(), b"b");
    assert_eq!(snapshot.check_root("."), RootCheck::Contained);
    assert_eq!(snapshot.read_walked("c.dart").unwrap(), b"c");
    let paths: Vec<String> = snapshot
        .inputs()
        .into_iter()
        .map(|input| input.path)
        .collect();
    assert_eq!(paths, ["c.dart", "lib/a.dart", "lib/src/b.dart"]);
    assert!(snapshot.problems.is_empty());
}

#[test]
fn a_missing_root_or_a_file_root_is_not_a_directory() {
    let tree = Tree::new(&[("lib/a.dart", "")]);
    let mut snapshot = Snapshot::new(&tree.path());
    assert_eq!(snapshot.check_root("absent"), RootCheck::NotDirectory);
    assert_eq!(snapshot.check_root("lib/a.dart"), RootCheck::NotDirectory);
}

#[test]
fn a_walked_file_over_the_size_limit_is_not_held() {
    let large = "a".repeat(super::MAX_FILE_BYTES as usize + 1);
    let tree = Tree::new(&[("lib/big.dart", &large)]);
    let mut snapshot = Snapshot::new(&tree.path());
    snapshot.check_root("lib");
    snapshot.listing("lib").unwrap();
    assert_eq!(snapshot.read_walked("lib/big.dart"), None);
    assert!(snapshot.size_gap("lib/big.dart").is_some());
    assert!(snapshot.inputs().is_empty());
}

// Containment: a file link and a directory link that leave the scan root are never read. The
// same tree also holds a root whose parent is a link out of the snapshot.
#[cfg(unix)]
#[test]
fn a_link_that_escapes_is_never_read_and_never_walked() {
    use std::os::unix::fs::symlink;

    let outside = Tree::new(&[("secret.dart", "secret"), ("dir/x.dart", "secret")]);
    let tree = Tree::new(&[("lib/a.dart", "a")]);
    let lib = tree.root.join("lib");
    symlink(outside.root.join("secret.dart"), lib.join("leak.dart")).unwrap();
    symlink(outside.root.join("dir"), lib.join("leak_dir")).unwrap();
    symlink(&outside.root, tree.root.join("away")).unwrap();
    let mut snapshot = Snapshot::new(&tree.path());
    assert_eq!(snapshot.check_root("lib"), RootCheck::Contained);
    let listing = snapshot.listing("lib").unwrap();
    assert!(listing.contains(&(
        "leak.dart".to_owned(),
        Entry::Link {
            to_directory: false
        }
    )));
    assert!(listing.contains(&("leak_dir".to_owned(), Entry::Link { to_directory: true })));
    assert_eq!(snapshot.read_walked("lib/leak.dart"), None);
    assert_eq!(snapshot.read_walked("lib/leak_dir/x.dart"), None);
    assert_eq!(snapshot.check_root("away"), RootCheck::Link);
    assert_eq!(snapshot.check_root("away/dir"), RootCheck::Escapes);
    assert_eq!(snapshot.read_walked("away/dir/x.dart"), None);
    assert_eq!(
        problems(&snapshot),
        [
            "Source is not a regular file: lib/leak.dart",
            "Source outside a checked root: away/dir/x.dart",
            "Source outside a checked root: lib/leak_dir/x.dart",
        ]
    );
    let read: Vec<String> = snapshot
        .inputs()
        .into_iter()
        .map(|input| input.path)
        .collect();
    assert!(read.is_empty(), "{read:?}");
}

#[cfg(unix)]
#[test]
fn a_snapshot_root_that_is_a_link_or_missing_does_not_open() {
    let tree = Tree::new(&[("lib/a.dart", "")]);
    let link = tree.root.join("lib/../link");
    std::os::unix::fs::symlink(tree.root.join("lib"), &link).unwrap();
    let error = Snapshot::open_root(&link.to_string_lossy()).err().unwrap();
    assert_eq!(error, "snapshot root must not be a symlink");
    let file = tree.root.join("lib/a.dart");
    let error = Snapshot::open_root(&file.to_string_lossy()).err().unwrap();
    assert_eq!(error, "snapshot root is not a directory");
    let error = Snapshot::open_root(&tree.root.join("absent").to_string_lossy())
        .err()
        .unwrap();
    assert!(
        error.starts_with("cannot resolve snapshot root: "),
        "{error}"
    );
    assert!(Snapshot::open_root(&tree.path()).is_ok());
    fs::remove_file(link).unwrap();
}
