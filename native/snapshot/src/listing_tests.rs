// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the Dart collector, which never follows a symbolic link and names each link as a
// gap. The listing must show a link as a link, also a link that leaves the snapshot or dangles.

use super::super::Snapshot;
use super::Entry;
use crate::test_tree::Tree;

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
    let problems: Vec<&String> = snapshot.problems.iter().collect();
    assert_eq!(problems, ["Unreadable source directory: absent"]);
}

#[test]
fn a_path_outside_the_snapshot_has_no_listing() {
    let tree = Tree::new(&[("lib/a.dart", "")]);
    let mut snapshot = Snapshot::new(&tree.path());
    assert_eq!(snapshot.listing("../x"), None);
    assert!(!snapshot.is_link("../x"));
}
