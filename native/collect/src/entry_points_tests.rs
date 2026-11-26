// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The entry points that manifests declare and files show (#2040, AD-1140).

use std::fs;

use super::*;
use crate::repository::tests::{scratch, Scratch};

fn tree(files: &[(&str, &str)]) -> (Scratch, Root) {
    let base = scratch("entry");
    for (path, text) in files {
        let target = base.join(path);
        fs::create_dir_all(target.parent().unwrap()).unwrap();
        fs::write(target, text).unwrap();
    }
    let root = Root::of(base.to_str().unwrap()).unwrap();
    (base, root)
}

/// The scanned files with a module name that the tests do not read.
fn scanned<'a>(paths: &[&'a str]) -> Vec<(&'a str, &'a str)> {
    paths.iter().map(|path| ("m", *path)).collect()
}

fn names(found: &EntryPoints) -> Vec<(EntryKind, EntryBasis, &str)> {
    found
        .entries
        .iter()
        .map(|entry| (entry.kind, entry.basis, entry.name.as_str()))
        .collect()
}

#[test]
fn python_scripts_and_a_main_module_each_carry_their_evidence() {
    let (_base, root) = tree(&[
        (
            "pyproject.toml",
            "[project.scripts]\ntool = \"pkg.cli:main\"\n[project.gui-scripts]\nwin = \"pkg.gui:run\"\n",
        ),
        ("pkg/__main__.py", "print('x')\n"),
    ]);
    let found = read(
        &root,
        Profile::Python,
        &[
            ("pkg.__main__", "pkg/__main__.py"),
            ("pkg.cli", "pkg/cli.py"),
        ],
    )
    .unwrap();
    assert_eq!(
        names(&found),
        [
            (EntryKind::PythonScript, EntryBasis::Declared, "tool"),
            (EntryKind::PythonGuiScript, EntryBasis::Declared, "win"),
            (
                EntryKind::PythonMainModule,
                EntryBasis::Observed,
                "pkg.__main__"
            ),
        ]
    );
    let first = &found.entries[0];
    assert_eq!(first.target.as_deref(), Some("pkg.cli:main"));
    assert_eq!(first.evidence.path, "pyproject.toml");
    assert_eq!(first.evidence.key.as_deref(), Some("project.scripts.tool"));
    assert_eq!(found.entries[2].evidence.key, None);
    assert!(found.unread.is_empty());
}

#[test]
fn a_python_project_without_entry_evidence_has_an_empty_proven_read() {
    let (_base, root) = tree(&[("pkg/a.py", "x = 1\n")]);
    let found = read(&root, Profile::Python, &scanned(&["pkg/a.py"])).unwrap();
    assert_eq!(found, EntryPoints::default());
}

#[test]
fn an_unreadable_pyproject_is_unread_not_empty() {
    let (_base, root) = tree(&[("pyproject.toml", "[project\n")]);
    let found = read(&root, Profile::Python, &[]).unwrap();
    assert!(found.entries.is_empty());
    assert_eq!(found.unread, ["pyproject.toml: cannot be read"]);
}

#[test]
fn cargo_bins_are_declared_and_the_default_files_are_observed() {
    let (_base, root) = tree(&[
        ("Cargo.toml", "[workspace]\nmembers = [\"app\"]\n"),
        (
            "app/Cargo.toml",
            "[package]\nname = \"app\"\nedition = \"2021\"\n[[bin]]\nname = \"tool\"\npath = \"src/tool_main.rs\"\n",
        ),
        ("app/src/main.rs", "fn main() {}\n"),
        ("app/src/bin/extra.rs", "fn main() {}\n"),
        ("app/src/bin/nested/main.rs", "fn main() {}\n"),
        ("app/src/lib.rs", ""),
    ]);
    let files = [
        "app/src/main.rs",
        "app/src/bin/extra.rs",
        "app/src/bin/nested/main.rs",
        "app/src/lib.rs",
    ];
    let found = read(&root, Profile::Rust, &scanned(&files)).unwrap();
    assert_eq!(
        names(&found),
        [
            (EntryKind::CargoBin, EntryBasis::Declared, "tool"),
            (EntryKind::CargoBin, EntryBasis::Observed, "app"),
            (EntryKind::CargoBin, EntryBasis::Observed, "extra"),
            (EntryKind::CargoBin, EntryBasis::Observed, "nested"),
        ]
    );
    let tool = &found.entries[0];
    assert_eq!(tool.target.as_deref(), Some("app/src/tool_main.rs"));
    assert_eq!(tool.evidence.path, "app/Cargo.toml");
    assert_eq!(tool.evidence.key.as_deref(), Some("bin.name=tool"));
    assert_eq!(found.entries[1].evidence.path, "app/src/main.rs");
}

#[test]
fn autobins_false_and_a_declared_name_suppress_the_observed_file() {
    let (_base, root) = tree(&[
        (
            "a/Cargo.toml",
            "[package]\nname = \"a\"\nautobins = false\n",
        ),
        ("a/src/main.rs", ""),
        (
            "b/Cargo.toml",
            "[package]\nname = \"b\"\n[[bin]]\nname = \"b\"\n",
        ),
        ("b/src/main.rs", ""),
    ]);
    let found = read(
        &root,
        Profile::Rust,
        &scanned(&["a/src/main.rs", "b/src/main.rs"]),
    )
    .unwrap();
    assert_eq!(
        names(&found),
        [(EntryKind::CargoBin, EntryBasis::Declared, "b")]
    );
    assert_eq!(found.entries[0].target, None);
}

#[test]
fn a_rust_manifest_that_cannot_be_parsed_is_unread() {
    let (_base, root) = tree(&[("Cargo.toml", "[package\n"), ("src/main.rs", "")]);
    let found = read(&root, Profile::Rust, &scanned(&["src/main.rs"])).unwrap();
    assert!(found.entries.is_empty());
    assert_eq!(found.unread, ["Cargo.toml: cannot be parsed"]);
}

#[test]
fn package_json_declares_bin_and_main() {
    let (_base, root) = tree(&[
        (
            "package.json",
            "{\"name\":\"lib\",\"main\":\"dist/index.js\",\"bin\":{\"lib-cli\":\"bin/cli.js\"}}",
        ),
        (
            "tools/package.json",
            "{\"name\":\"solo\",\"bin\":\"run.js\"}",
        ),
        ("src/index.ts", ""),
    ]);
    let found = read(
        &root,
        Profile::TypeScript,
        &scanned(&["src/index.ts", "tools/run.ts"]),
    )
    .unwrap();
    assert_eq!(
        names(&found),
        [
            (EntryKind::PackageBin, EntryBasis::Declared, "lib-cli"),
            (EntryKind::PackageMain, EntryBasis::Declared, "lib"),
            (EntryKind::PackageBin, EntryBasis::Declared, "solo"),
        ]
    );
    assert_eq!(
        found.entries[0].evidence.key.as_deref(),
        Some("bin.lib-cli")
    );
    assert_eq!(found.entries[1].target.as_deref(), Some("dist/index.js"));
}

#[test]
fn a_package_json_that_cannot_be_read_is_unread() {
    let (_base, root) = tree(&[("package.json", "{\"bin\": 3, \"main\": []}")]);
    let found = read(&root, Profile::TypeScript, &[]).unwrap();
    assert!(found.entries.is_empty());
    assert_eq!(found.unread.len(), 2);
}

#[test]
fn a_language_without_a_reader_has_no_list() {
    let (_base, root) = tree(&[("pubspec.yaml", "name: x\n")]);
    assert_eq!(read(&root, Profile::Dart, &[]), None);
}

#[test]
fn a_declared_path_or_an_edition_2015_package_with_bins_hides_the_default_files() {
    let (_base, root) = tree(&[
        (
            "renamed/Cargo.toml",
            "[package]\nname = \"demo\"\nedition = \"2021\"\n[[bin]]\nname = \"custom\"\npath = \"./src/main.rs\"\n",
        ),
        ("renamed/src/main.rs", ""),
        (
            "old/Cargo.toml",
            "[package]\nname = \"demo\"\n[[bin]]\nname = \"tool\"\npath = \"src/start.rs\"\n",
        ),
        ("old/src/main.rs", ""),
        ("old/src/bin/extra.rs", ""),
        (
            "inherited/Cargo.toml",
            "[package]\nname = \"inh\"\nedition.workspace = true\n[[bin]]\nname = \"x\"\n",
        ),
        ("inherited/src/main.rs", ""),
    ]);
    let files = scanned(&[
        "renamed/src/main.rs",
        "old/src/main.rs",
        "old/src/bin/extra.rs",
        "inherited/src/main.rs",
    ]);
    let found = read(&root, Profile::Rust, &files).unwrap();
    assert_eq!(
        names(&found),
        [
            (EntryKind::CargoBin, EntryBasis::Declared, "x"),
            (EntryKind::CargoBin, EntryBasis::Declared, "tool"),
            (EntryKind::CargoBin, EntryBasis::Declared, "custom"),
        ]
    );
    assert_eq!(found.unread.len(), 1);
    assert!(found.unread[0].starts_with("inherited/Cargo.toml: the edition"));
}

#[test]
fn an_edition_2015_package_without_bins_still_finds_its_default_files() {
    let (_base, root) = tree(&[
        ("Cargo.toml", "[package]\nname = \"demo\"\n"),
        ("src/main.rs", ""),
    ]);
    let found = read(&root, Profile::Rust, &scanned(&["src/main.rs"])).unwrap();
    assert_eq!(
        names(&found),
        [(EntryKind::CargoBin, EntryBasis::Observed, "demo")]
    );
}

#[test]
fn a_scoped_package_name_installs_its_last_part_as_the_command() {
    let (_base, root) = tree(&[
        (
            "package.json",
            "{\"name\":\"@acme/tool\",\"bin\":\"cli.js\"}",
        ),
        (
            "x/package.json",
            "{\"name\":\"@acme/multi\",\"bin\":{\"@acme/one\":\"one.js\"}}",
        ),
    ]);
    let found = read(&root, Profile::TypeScript, &scanned(&["x/a.ts"])).unwrap();
    assert_eq!(
        names(&found),
        [
            (EntryKind::PackageBin, EntryBasis::Declared, "tool"),
            (EntryKind::PackageBin, EntryBasis::Declared, "one"),
        ]
    );
    assert_eq!(found.entries[0].evidence.key.as_deref(), Some("bin"));
    assert_eq!(
        found.entries[1].evidence.key.as_deref(),
        Some("bin.@acme/one")
    );
}
