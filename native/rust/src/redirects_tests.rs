// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the named gaps of AD-502. Each text is a file that Cargo reads.

use super::*;
use archkeel_snapshot::test_tree::Tree;

const APP: &str = "[package]\nname = \"app\"\n[dependencies]\nbase-crate = \"1\"\n";
const PATCH: &str = "[patch.crates-io]\nbase-crate = { path = \"base\" }\n";

fn run(files: &[(&str, &str)]) -> Vec<(String, String)> {
    let root = Tree::new(files);
    let mut source = Snapshot::new(&root.path());
    let manifests: Vec<String> = files
        .iter()
        .map(|(name, _)| (*name).to_owned())
        .filter(|name| name.ends_with("Cargo.toml"))
        .collect();
    unread(&mut source, &manifests)
}

#[test]
fn a_file_that_parses_is_no_gap_also_when_it_redirects() {
    for (file, text) in [
        (".cargo/config.toml", "[build]\njobs = 2\n"),
        (".cargo/config.toml", PATCH),
        (".cargo/config", "paths = [\"base\"]\n"),
        (
            "Cargo.toml",
            "[workspace]\n[patch.crates-io]\nbase-crate = { path = \"base\" }\n",
        ),
    ] {
        let files = [("crates/app/Cargo.toml", APP), (file, text)];
        assert_eq!(run(&files), Vec::new(), "{file}: {text}");
    }
}

#[test]
fn a_config_that_cannot_be_parsed_is_a_gap() {
    for file in [".cargo/config.toml", "crates/.cargo/config"] {
        let files = [("crates/app/Cargo.toml", APP), (file, "= nope")];
        let found = run(&files);
        assert_eq!(found.len(), 1, "{file}");
        assert_eq!(found[0].0, file);
    }
}

#[test]
fn a_manifest_of_a_scanned_crate_is_reported_by_the_crate_reader() {
    let files = [
        ("crates/app/Cargo.toml", APP),
        ("crates/bad/Cargo.toml", "= nope"),
    ];
    assert_eq!(run(&files), Vec::new());
}
