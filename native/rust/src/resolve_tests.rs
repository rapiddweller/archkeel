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
            ("serde_json".to_owned(), "serde_json".to_owned()),
            ("renamed".to_owned(), "real_name".to_owned()),
            ("my_app".to_owned(), "my_app".to_owned()),
        ]),
        features: BTreeSet::new(),
    };
    Crate {
        ident: "my_app".to_owned(),
        dir: String::new(),
        manifest,
        roots: Vec::new(),
        primary: None,
    }
}

fn named(root: &str, declared: &[&str]) -> Option<Named> {
    let declared = declared.iter().map(|name| (*name).to_owned()).collect();
    classify(root, &krate(), &declared, false)
}

#[test]
fn a_dependency_and_a_renamed_dependency_name_their_package() {
    assert_eq!(
        named("serde_json", &[]),
        Some(Named::Package("serde_json".to_owned()))
    );
    assert_eq!(
        named("renamed", &[]),
        Some(Named::Package("real_name".to_owned()))
    );
}

#[test]
fn a_sysroot_crate_is_named_without_a_dependency() {
    for name in ["std", "core", "alloc"] {
        assert_eq!(named(name, &[]), Some(Named::Sysroot(name.to_owned())));
    }
}

#[test]
fn a_local_item_a_relative_root_and_an_unknown_name_are_no_edge() {
    assert_eq!(named("serde_json", &["serde_json"]), None);
    assert_eq!(named("std", &["std"]), None);
    for root in ["crate", "self", "super", "Self", "Vec", "Option", "missing"] {
        assert_eq!(named(root, &[]), None, "{root}");
    }
}

#[test]
fn the_package_itself_is_no_edge() {
    assert_eq!(named("my_app", &[]), None);
}

#[test]
fn a_path_that_starts_with_two_colons_names_a_crate_and_no_local_item_hides_it() {
    let declared = ["serde_json".to_owned()].into_iter().collect();
    let found = classify("serde_json", &krate(), &declared, true);
    assert_eq!(found, Some(Named::Package("serde_json".to_owned())));
    assert_eq!(
        classify(
            "std",
            &krate(),
            &["std".to_owned()].into_iter().collect(),
            true
        ),
        Some(Named::Sysroot("std".to_owned()))
    );
    // `::crate` and `::missing` are no crate of this one.
    assert_eq!(classify("crate", &krate(), &BTreeSet::new(), true), None);
    assert_eq!(classify("missing", &krate(), &BTreeSet::new(), true), None);
}
