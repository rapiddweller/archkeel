// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the search for the Cargo settings of the repository that can change a registry crate
// (AD-774). A cache marker does not affect Cargo's configuration search (#1859).

use archkeel_snapshot::test_tree::Tree;
use archkeel_snapshot::Snapshot;

use super::{configs, manifest, package_of_spec, Lines, Overrides};

const REPLACED: &str = "[build]\njobs = 1\n\n[source.crates-io]\nreplace-with = \"vendored\"\n";
const CACHE_TAG: &str = "Signature: 8a477f597d28d172789f06886806bc55\n";

fn scan(tree: &Tree) -> (Overrides, bool) {
    let mut snapshot = Snapshot::new(&tree.path());
    let found = configs(&mut snapshot);
    (found, snapshot.problems.is_empty())
}

fn every(tree: &Tree) -> (bool, bool) {
    let (found, clean) = scan(tree);
    (found.all.is_some(), clean)
}

#[test]
fn a_replacement_of_crates_io_at_any_level_changes_every_crate_with_its_line() {
    let tree = Tree::new(&[
        ("Cargo.toml", ""),
        ("tools/deep/.cargo/config.toml", REPLACED),
    ]);
    let (found, clean) = scan(&tree);
    let cited = found.all.expect("the replacement is read");
    assert!(clean);
    assert_eq!(cited.rel, "tools/deep/.cargo/config.toml");
    assert_eq!(
        (cited.line, cited.excerpt.as_str()),
        (5, "replace-with = \"vendored\"")
    );
    let dotted = Tree::new(&[(".cargo/config", "source.crates-io.replace-with = \"v\"\n")]);
    assert_eq!(scan(&dotted).0.all.map(|c| c.line), Some(1));
}

#[test]
fn a_configuration_without_a_source_setting_changes_nothing() {
    let tree = Tree::new(&[
        ("Cargo.toml", ""),
        (
            ".cargo/config.toml",
            "[build]\njobs = 1\n[alias]\nb = \"build\"\n",
        ),
    ]);
    let (found, clean) = scan(&tree);
    assert!(found.all.is_none() && found.packages.is_empty() && clean);
}

#[test]
fn a_patch_in_a_configuration_changes_the_named_crate_and_a_paths_override_every_crate() {
    let patch = "[patch.crates-io]\nserde_derive = { path = \"x\" }\nalias = { path = \"y\", package = \"schemars\" }\n";
    let tree = Tree::new(&[(".cargo/config.toml", patch)]);
    let (found, _) = scan(&tree);
    assert!(found.all.is_none());
    assert_eq!(found.packages["serde_derive"].line, 2);
    assert_eq!(found.packages["schemars"].line, 3);
    let paths = Tree::new(&[(".cargo/config", "paths = [\"../serde\"]\n")]);
    assert!(scan(&paths).0.all.is_some());
}

#[test]
fn a_patch_and_a_replace_of_a_manifest_change_the_named_crates() {
    let text = "[workspace]\n\n[patch.crates-io.serde]\npath = \"s\"\n\n[replace]\n\"serde_derive:1.0.229\" = { path = \"d\" }\n";
    let table = crate::toml::parse(text).expect("the manifest parses");
    let mut found = Overrides::default();
    manifest(&table, &Lines::new("Cargo.toml", text), &mut found);
    assert!(found.all.is_none());
    assert_eq!(found.packages["serde"].line, 3);
    assert_eq!(found.packages["serde_derive"].line, 7);
    assert_eq!(
        package_of_spec("https://github.com/rust-lang/crates.io-index#serde@1.0.229"),
        Some("serde")
    );
    assert_eq!(package_of_spec("https://example.com/x#1.0"), None);
}

#[test]
fn a_configuration_that_does_not_parse_changes_every_crate() {
    let tree = Tree::new(&[(".cargo/config.toml", "[source\n")]);
    assert_eq!(every(&tree), (true, true));
}

#[test]
fn a_marker_does_not_change_which_cargo_config_is_read() {
    for marker in [
        None,
        Some(("target/CACHEDIR.TAG", "invalid")),
        Some(("target/CACHEDIR.TAG", CACHE_TAG)),
        Some(("target/.rustc_info.json", "{}")),
    ] {
        let path = "target/debug/nested/.cargo/config.toml";
        let mut files = vec![("Cargo.toml", ""), (path, "paths = [\"local-input\"]\n")];
        files.extend(marker);
        let tree = Tree::new(&files);
        let (found, clean) = scan(&tree);
        assert_eq!(found.all.expect("the paths override is read").rel, path);
        assert!(clean);

        files[1].1 = "[build]\njobs = 1\n";
        assert_eq!(every(&Tree::new(&files)), (false, true));
    }
}

#[test]
fn the_config_of_the_build_directory_itself_still_withholds_the_model() {
    let tree = Tree::new(&[
        ("Cargo.toml", ""),
        ("target/CACHEDIR.TAG", ""),
        ("target/.cargo/config.toml", REPLACED),
    ]);
    assert_eq!(every(&tree), (true, true));
}

#[cfg(unix)]
#[test]
fn a_directory_that_cannot_be_listed_below_a_build_directory_withholds_proof() {
    use std::os::unix::fs::PermissionsExt;

    let tree = Tree::new(&[
        ("Cargo.toml", ""),
        ("target/CACHEDIR.TAG", CACHE_TAG),
        ("target/debug/deps/x", ""),
    ]);
    let locked = tree.root.join("target/debug");
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o000)).unwrap();
    // A process that is allowed to read it (root) cannot show the failure.
    let readable = std::fs::read_dir(&locked).is_ok();
    let result = every(&tree);
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o755)).unwrap();
    if !readable {
        assert_eq!(result, (true, false));
    }
}

#[cfg(unix)]
#[test]
fn a_link_below_a_cache_tag_withholds_proof_without_reading_its_target() {
    use std::os::unix::fs::symlink;

    let outside = Tree::new(&[(".cargo/config.toml", REPLACED)]);
    let tree = Tree::new(&[("target/CACHEDIR.TAG", CACHE_TAG), ("target/debug/x", "")]);
    symlink(&outside.root, tree.root.join("target/debug/nested")).unwrap();
    let (found, clean) = scan(&tree);
    assert_eq!(
        found.all.expect("the link withholds proof").rel,
        "target/debug/nested"
    );
    assert!(clean);
}

#[cfg(unix)]
#[test]
fn a_dangling_cargo_config_link_below_a_cache_tag_withholds_proof() {
    use std::os::unix::fs::symlink;

    let tree = Tree::new(&[
        ("target/CACHEDIR.TAG", CACHE_TAG),
        ("target/debug/.cargo/keep", ""),
    ]);
    let path = "target/debug/.cargo/config.toml";
    symlink("missing", tree.root.join(path)).unwrap();
    let (found, clean) = scan(&tree);
    assert_eq!(found.all.expect("the config is unreadable").rel, path);
    assert!(clean);
}
#[cfg(unix)]
#[test]
fn a_directory_that_cannot_be_listed_outside_a_build_directory_stays_a_problem() {
    use std::os::unix::fs::PermissionsExt;

    let tree = Tree::new(&[("Cargo.toml", ""), ("src/deps/x", "")]);
    let locked = tree.root.join("src/deps");
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o000)).unwrap();
    let readable = std::fs::read_dir(&locked).is_ok();
    let result = every(&tree);
    std::fs::set_permissions(&locked, std::fs::Permissions::from_mode(0o755)).unwrap();
    if !readable {
        assert_eq!(result, (true, false));
    }
}
