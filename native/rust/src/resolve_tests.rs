// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the crate edges. Each case is one rule of the resolution.

use std::collections::BTreeMap;

use super::*;
use crate::manifest::Manifest;

fn krate() -> Crate {
    let manifest = Manifest {
        package: "my-app".to_owned(),
        lib_name: None,
        lib_path: None,
        bins: Vec::new(),
        build: None,
        dependencies: BTreeMap::from([
            ("json_dep".to_owned(), "json_dep".to_owned()),
            ("renamed".to_owned(), "real_name".to_owned()),
            ("my_app".to_owned(), "my_app".to_owned()),
        ]),
        declared: Vec::new(),
        unknown: Vec::new(),
        features: BTreeSet::new(),
        edition: Some("2021".to_owned()),
    };
    Crate {
        ident: "my_app".to_owned(),
        dir: String::new(),
        manifest,
        text: String::new(),
        lines: crate::manifest_lines::LineIndex::new(""),
        roots: Vec::new(),
        primary: None,
    }
}

fn found(root: &str, names: &[&str], absolute: bool) -> Option<Found> {
    let names = names.iter().map(|name| (*name).to_owned()).collect();
    classify(root, &krate(), &names, absolute)
}

fn edge(package: &str) -> Option<Found> {
    Some(Found::Edge(Named::Package(package.to_owned())))
}

#[test]
fn a_dependency_and_a_renamed_dependency_are_edges() {
    assert_eq!(found("json_dep", &[], false), edge("json_dep"));
    assert_eq!(found("renamed", &[], false), edge("real_name"));
}

#[test]
fn a_sysroot_crate_is_an_edge_without_a_dependency() {
    for name in "std core alloc".split(' ') {
        let sysroot = Some(Found::Edge(Named::Sysroot(name.to_owned())));
        assert_eq!(found(name, &[], false), sysroot);
    }
}

#[test]
fn a_crate_name_that_the_file_also_declares_is_unknown_never_an_edge_and_never_hidden() {
    // The scan does not decide which one Rust picks: a type, a module, a function, an import.
    assert_eq!(
        found("json_dep", &["json_dep"], false),
        Some(Found::Shadowed)
    );
    assert_eq!(found("renamed", &["renamed"], false), Some(Found::Shadowed));
    assert_eq!(found("std", &["std"], false), Some(Found::Shadowed));
    // Another name of the file changes nothing.
    assert_eq!(
        found("json_dep", &["Other", "serde"], false),
        edge("json_dep")
    );
}

#[test]
fn a_path_that_starts_with_two_colons_is_the_crate_whatever_the_file_declares() {
    assert_eq!(found("json_dep", &["json_dep"], true), edge("json_dep"));
    let sysroot = Some(Found::Edge(Named::Sysroot("std".to_owned())));
    assert_eq!(found("std", &["std"], true), sysroot);
    assert_eq!(found("crate", &[], true), None);
    assert_eq!(found("missing", &[], true), None);
}

#[test]
fn a_local_root_a_prelude_name_an_unknown_name_and_the_package_itself_are_no_edge() {
    for root in ["crate", "self", "super", "Self"] {
        assert_eq!(found(root, &[root], false), None, "{root}");
        assert_eq!(found(root, &[], false), None, "{root}");
    }
    for root in ["Vec", "Option", "missing", "my_app"] {
        assert_eq!(found(root, &[], false), None, "{root}");
    }
}
