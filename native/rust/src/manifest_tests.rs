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
        "[package]\nname = \"app-core\"\n[dependencies]\njson-dep = \"1\"\n\
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
            ("json_dep", "json_dep"),
            ("libc", "libc"),
            ("old", "new_name"),
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

#[test]
fn every_dependency_form_is_declared_with_its_kind_and_the_underscore_forms_are_read() {
    let found = manifest(
        "[package]\nname = \"a\"\n[dependencies]\nn = \"1\"\n[dev_dependencies]\nd = \"1\"\n\
         [build_dependencies]\nb = \"1\"\n[target.'cfg(unix)'.dev-dependencies]\nt = \"1\"\n\
         [dependencies.long]\nversion = \"1\"\n",
        "",
    );
    let declared: Vec<(&str, Kind)> = found
        .declared
        .iter()
        .map(|dep| (dep.key.as_str(), dep.kind))
        .collect();
    assert!(declared.contains(&("n", Kind::Normal)));
    assert!(declared.contains(&("d", Kind::Dev)));
    assert!(declared.contains(&("b", Kind::Build)));
    assert!(declared.contains(&("t", Kind::Dev)));
    assert!(declared.contains(&("long", Kind::Normal)));
    assert!(found.unknown.is_empty(), "{:?}", found.unknown);
    // Source can name a crate of an underscore section.
    assert_eq!(found.dependencies.get("d").map(String::as_str), Some("d"));
}

#[test]
fn a_dependency_table_or_form_that_the_reader_does_not_know_is_kept_as_unknown() {
    let found = manifest(
        "[package]\nname = \"a\"\n[dependancies]\nx = \"1\"\n[target.'cfg(unix)'.build_deps]\ny = \"1\"\n\
         [dependencies]\nz = 1\n",
        "",
    );
    assert_eq!(
        found.unknown,
        [
            "A dependency table that the reader does not know: [dependancies]",
            "A dependency table that the reader does not know: [target.cfg(unix).build_deps]",
            "A dependency has a form that the reader does not know: z",
        ]
    );
}

const REMOTE_MANIFEST: &str = "[package]\nname = \"app\"\n[dependencies]\n\
     reg = \"1\"\ngit-dep = { git = \"https://example.invalid/g.git\" }\n\
     near = { path = \"../near\", version = \"1\" }\n\
     shared-path = { workspace = true }\nshared-reg = { workspace = true }\n";
const REMOTE_WORKSPACE: &str = "[workspace.dependencies]\n\
     shared-path = { path = \"../shared\" }\nshared-reg = \"2\"\n";

#[test]
fn only_a_registry_or_git_entry_makes_a_dependency_remote() {
    let found = manifest(REMOTE_MANIFEST, REMOTE_WORKSPACE);
    let remote: Vec<&str> = found.remote.iter().map(String::as_str).collect();
    assert_eq!(remote, ["git_dep", "reg", "shared_reg"]);
    assert!(found.unknown.is_empty());
}

#[test]
fn a_package_with_a_path_entry_and_a_registry_entry_is_not_remote() {
    let found = manifest(
        "[package]\nname = \"app\"\n[dependencies]\nbase = { path = \"../base\" }\n\
         [dev-dependencies]\nbase = \"1\"\n[build-dependencies]\nother = { path = \"o\" }\n",
        "",
    );
    assert!(found.remote.is_empty());
}

#[test]
fn a_workspace_dependency_without_an_entry_is_unknown_and_not_remote() {
    let found = manifest(
        "[package]\nname = \"app\"\n[dependencies]\nlost = { workspace = true }\n",
        "[workspace.dependencies]\n",
    );
    assert!(found.remote.is_empty());
    assert_eq!(
        found.unknown,
        ["A dependency of the workspace has no entry in [workspace.dependencies]: lost"]
    );
}
