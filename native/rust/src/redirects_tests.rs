// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the rule of AD-502. Each text is a place that Cargo reads for a redirect.

use super::*;
use archkeel_snapshot::test_tree::Tree;

const APP: &str = "[package]\nname = \"app\"\n[dependencies]\nbase-crate = \"1\"\n";

fn run(files: &[(&str, &str)], dir: &str) -> Redirect {
    let root = Tree::new(files);
    let mut source = Snapshot::new(&root.path());
    let mut tables = BTreeMap::new();
    let text = std::fs::read_to_string(
        std::path::Path::new(&root.path())
            .join(dir)
            .join("Cargo.toml"),
    )
    .unwrap();
    let table = toml::parse(&text).unwrap();
    of(&mut source, &mut tables, (dir, &table), None)
}

#[test]
fn no_place_that_redirects_leaves_the_name_a_registry_name() {
    let files = [
        ("crates/app/Cargo.toml", APP),
        ("Cargo.toml", "[workspace]\n"),
    ];
    assert_eq!(run(&files, "crates/app"), Redirect::None);
}

#[test]
fn a_cargo_config_of_the_crate_or_a_directory_above_can_redirect() {
    let patch = "[patch.crates-io]\nbase-crate = { path = \"base\" }\n";
    for (config, text) in [
        ("crates/app/.cargo/config.toml", patch),
        ("crates/.cargo/config.toml", patch),
        (".cargo/config.toml", patch),
        (".cargo/config", patch),
        (".cargo/config.toml", "paths = [\"base\"]\n"),
        (
            ".cargo/config.toml",
            "[source.crates-io]\nreplace-with = \"v\"\n",
        ),
    ] {
        let files = [("crates/app/Cargo.toml", APP), (config, text)];
        assert_eq!(
            run(&files, "crates/app"),
            Redirect::Possible,
            "{config}: {text}"
        );
    }
}

#[test]
fn a_cargo_config_without_a_redirect_is_read_and_changes_nothing() {
    let files = [
        ("crates/app/Cargo.toml", APP),
        (".cargo/config.toml", "[build]\njobs = 2\n"),
    ];
    assert_eq!(run(&files, "crates/app"), Redirect::None);
}

#[test]
fn a_cargo_config_that_cannot_be_parsed_is_a_gap() {
    let files = [
        ("crates/app/Cargo.toml", APP),
        (".cargo/config.toml", "= nope"),
    ];
    assert!(matches!(run(&files, "crates/app"), Redirect::Unread(_)));
}

#[test]
fn a_workspace_root_that_package_workspace_names_is_read() {
    let app = format!(
        "[package]\nname = \"app\"\nworkspace = \"../ws\"\n{}",
        &APP[APP.find("[dep").unwrap()..]
    );
    let patched = "[workspace]\n[patch.crates-io]\nbase-crate = { path = \"../base\" }\n";
    let files = [
        ("crates/app/Cargo.toml", app.as_str()),
        ("crates/ws/Cargo.toml", patched),
    ];
    assert_eq!(run(&files, "crates/app"), Redirect::Possible);
    let files = [
        ("crates/app/Cargo.toml", app.as_str()),
        ("crates/ws/Cargo.toml", "[workspace]\n"),
    ];
    assert_eq!(run(&files, "crates/app"), Redirect::None);
}

#[test]
fn a_workspace_root_that_is_missing_or_outside_the_scan_root_is_a_gap() {
    let missing = APP.replace("name = \"app\"", "name = \"app\"\nworkspace = \"../ws\"");
    let files = [("crates/app/Cargo.toml", missing.as_str())];
    assert!(matches!(run(&files, "crates/app"), Redirect::Unread(_)));
    let outside = APP.replace(
        "name = \"app\"",
        "name = \"app\"\nworkspace = \"../../../up\"",
    );
    let files = [("crates/app/Cargo.toml", outside.as_str())];
    assert!(matches!(run(&files, "crates/app"), Redirect::Unread(_)));
}
