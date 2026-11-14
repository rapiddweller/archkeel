// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the rule of AD-502. Each text is a file that Cargo reads for a redirect.

use super::*;
use archkeel_snapshot::test_tree::Tree;

const APP: &str = "[package]\nname = \"app\"\n[dependencies]\nbase-crate = \"1\"\n";
const PATCH: &str = "[patch.crates-io]\nbase-crate = { path = \"base\" }\n";

fn run(files: &[(&str, &str)]) -> Outcome {
    let root = Tree::new(files);
    let mut source = Snapshot::new(&root.path());
    let manifests: Vec<String> = files
        .iter()
        .map(|(name, _)| (*name).to_owned())
        .filter(|name| name.ends_with("Cargo.toml"))
        .collect();
    scan(&mut source, &manifests)
}

#[test]
fn no_file_that_redirects_leaves_the_name_a_registry_name() {
    let files = [
        ("crates/app/Cargo.toml", APP),
        ("Cargo.toml", "[workspace]\n"),
        (".cargo/config.toml", "[build]\njobs = 2\n"),
    ];
    assert_eq!(run(&files), Outcome::default());
}

#[test]
fn a_redirect_in_any_manifest_or_config_of_the_snapshot_turns_the_rule_off() {
    for (file, text) in [
        (
            "crates/ws/Cargo.toml",
            "[workspace]\n[patch.crates-io]\nbase-crate = { path = \"../base\" }\n",
        ),
        (
            "crates/ws/Cargo.toml",
            "[workspace]\n[replace]\n\"base-crate:1.0.0\" = { path = \"../base\" }\n",
        ),
        ("crates/app/.cargo/config.toml", PATCH),
        ("crates/ws/.cargo/config.toml", PATCH),
        ("crates/.cargo/config.toml", PATCH),
        (".cargo/config.toml", PATCH),
        (".cargo/config", PATCH),
        (".cargo/config.toml", "paths = [\"base\"]\n"),
        (
            ".cargo/config.toml",
            "[source.crates-io]\nreplace-with = \"v\"\n",
        ),
        (".cargo/config.toml", "include = [\"extra.toml\"]\n"),
    ] {
        let sibling = ("crates/ws/Cargo.toml", "[package]\nname = \"ws\"\n");
        let files = [("crates/app/Cargo.toml", APP), sibling, (file, text)];
        let files: Vec<_> = files
            .into_iter()
            .filter(|f| f.0 != file || f.1 == text)
            .collect();
        let found = run(&files);
        assert!(found.redirected, "{file}: {text}");
        assert!(found.unread.is_empty(), "{file}: {text}");
    }
}

#[test]
fn a_config_that_cannot_be_parsed_turns_the_rule_off_and_is_a_gap() {
    let files = [
        ("crates/app/Cargo.toml", APP),
        (".cargo/config.toml", "= nope"),
    ];
    let found = run(&files);
    assert!(found.redirected);
    assert_eq!(found.unread.len(), 1);
    assert_eq!(found.unread[0].0, ".cargo/config.toml");
}

#[test]
fn a_manifest_that_cannot_be_parsed_turns_the_rule_off_and_is_reported_by_the_crate_reader() {
    let files = [
        ("crates/app/Cargo.toml", APP),
        ("crates/bad/Cargo.toml", "= nope"),
    ];
    let found = run(&files);
    assert!(found.redirected);
    assert!(found.unread.is_empty());
}
