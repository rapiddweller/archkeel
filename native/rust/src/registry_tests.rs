// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the search for a Cargo config below a scan root. A build directory that a parallel
// build changes must not make the scan unreadable (#880).

use archkeel_snapshot::test_tree::Tree;
use archkeel_snapshot::Snapshot;

use super::overrides;

fn blocked(tree: &Tree) -> (bool, bool) {
    let mut snapshot = Snapshot::new(&tree.path());
    let found = overrides(&mut snapshot, &[".".to_owned()]);
    (found, snapshot.problems.is_empty())
}

#[test]
fn a_cargo_config_below_a_build_directory_is_not_searched() {
    let tagged = Tree::new(&[
        ("Cargo.toml", ""),
        ("target/CACHEDIR.TAG", ""),
        ("target/debug/.cargo/config.toml", ""),
    ]);
    assert_eq!(blocked(&tagged), (false, true));
    let plain = Tree::new(&[
        ("Cargo.toml", ""),
        ("out/debug/.cargo/config.toml", ""),
        ("out/note.txt", ""),
    ]);
    assert_eq!(blocked(&plain), (true, true));
}

#[test]
fn the_config_of_the_build_directory_itself_still_withholds_the_model() {
    let tree = Tree::new(&[
        ("Cargo.toml", ""),
        ("target/CACHEDIR.TAG", ""),
        ("target/.cargo/config.toml", ""),
    ]);
    assert_eq!(blocked(&tree), (true, true));
}

#[cfg(unix)]
#[test]
fn a_directory_that_cannot_be_listed_below_a_build_directory_is_no_problem() {
    use std::os::unix::fs::PermissionsExt;

    let tree = Tree::new(&[
        ("Cargo.toml", ""),
        ("target/CACHEDIR.TAG", ""),
        ("target/debug/deps/x", ""),
    ]);
    let locked = tree.root.join("target/debug");
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o000)).unwrap();
    // A process that is allowed to read it (root) cannot show the failure.
    let readable = std::fs::read_dir(&locked).is_ok();
    let result = blocked(&tree);
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o755)).unwrap();
    if !readable {
        assert_eq!(result, (false, true));
    }
}

#[cfg(unix)]
#[test]
fn a_directory_that_cannot_be_listed_outside_a_build_directory_stays_a_problem() {
    use std::os::unix::fs::PermissionsExt;

    let tree = Tree::new(&[("Cargo.toml", ""), ("src/deps/x", "")]);
    let locked = tree.root.join("src/deps");
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o000)).unwrap();
    let readable = std::fs::read_dir(&locked).is_ok();
    let result = blocked(&tree);
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o755)).unwrap();
    if !readable {
        assert_eq!(result, (true, false));
    }
}
