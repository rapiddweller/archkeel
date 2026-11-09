// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: crate discovery. Each text is the shape of a real manifest.

use super::*;
use crate::toml::parse;

fn manifest(text: &str, workspace: &str) -> Manifest {
    let workspace = workspace_dependencies(&parse(workspace).unwrap());
    read(&parse(text).unwrap(), &workspace).unwrap()
}

#[test]
fn a_dependency_has_the_name_that_source_writes() {
    let found = manifest(
        "[package]\nname = \"app-core\"\n[dependencies]\nserde-json = \"1\"\n\
         old = { package = \"new-name\", version = \"1\" }\n\
         [dev-dependencies]\nhelper = { workspace = true }\n\
         [build-dependencies]\nsha2 = \"0.10\"\n\
         [target.'cfg(unix)'.dependencies]\nlibc = \"0.2\"\n",
        "[workspace.dependencies]\nhelper = { path = \"h\", package = \"real-helper\" }\n",
    );
    let names: Vec<(&str, &str)> = found
        .dependencies
        .iter()
        .map(|(alias, package)| (alias.as_str(), package.as_str()))
        .collect();
    assert_eq!(
        names,
        [
            ("helper", "real_helper"),
            ("libc", "libc"),
            ("old", "new_name"),
            ("serde_json", "serde_json"),
            ("sha2", "sha2"),
        ]
    );
}

#[test]
fn a_virtual_workspace_has_no_package() {
    let table = parse("[workspace]\nmembers = [\"a\"]\n").unwrap();
    assert!(is_workspace(&table));
    assert!(read(&table, &Table::new()).is_none());
}

#[test]
fn declared_features_include_optional_dependencies_and_a_renamed_lib_is_kept() {
    let found = manifest(
        "[package]\nname = \"a\"\nbuild = \"../shared/build.rs\"\n[lib]\nname = \"b\"\npath = \"x.rs\"\n\
         [features]\ndump = []\n[dependencies]\nopt = { version = \"1\", optional = true }\n\
         [[bin]]\nname = \"a\"\n[[bin]]\nname = \"tool\"\npath = \"t/main.rs\"\n",
        "",
    );
    assert_eq!(
        found
            .features
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>(),
        ["dump", "opt"]
    );
    assert_eq!(found.lib_name.as_deref(), Some("b"));
    assert_eq!(found.lib_path.as_deref(), Some("x.rs"));
    assert_eq!(found.build, Some(Some("../shared/build.rs".to_owned())));
    let bins: Vec<_> = found.bins.iter().map(|bin| bin.path.as_str()).collect();
    assert_eq!(bins, ["src/main.rs", "t/main.rs"]);
}

#[test]
fn build_false_turns_the_script_off() {
    let found = manifest("[package]\nname = \"a\"\nbuild = false\n", "");
    assert_eq!(found.build, None);
}
