// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package map proves a package external only from a hosted, SDK or remote git origin that
//! no workspace contradicts (AD-800).

use super::{origin, remote, Origin, PackageMap};
use crate::import_survey::names::GapName;

fn map(declared: &[(&str, Origin)]) -> PackageMap {
    PackageMap {
        read: true,
        declared: declared
            .iter()
            .map(|(name, origin)| ((*name).to_owned(), origin.clone()))
            .collect(),
        ..PackageMap::default()
    }
}

fn gap(map: &PackageMap, package: &str) -> Option<GapName> {
    map.external(package).err().map(|(name, _)| name)
}

#[test]
fn a_hosted_sdk_or_remote_git_dependency_is_external() {
    let found = map(&[
        ("http", Origin::Hosted),
        ("flutter", Origin::Sdk),
        ("lints", Origin::RemoteGit),
    ]);
    for package in ["http", "flutter", "lints"] {
        assert_eq!(gap(&found, package), None, "{package}");
    }
}

#[test]
fn a_local_an_undeclared_or_a_member_package_is_a_gap() {
    let mut found = map(&[("other", Origin::Local("path"))]);
    assert_eq!(gap(&found, "other"), Some(GapName::LocalPackage));
    assert_eq!(gap(&found, "nobody"), Some(GapName::UndeclaredPackage));
    found.declared.insert("member".to_owned(), Origin::Hosted);
    found.members.insert("member".to_owned());
    assert_eq!(gap(&found, "member"), Some(GapName::LocalPackage));
}

#[test]
fn a_workspace_above_the_root_can_resolve_any_name() {
    let mut found = map(&[("flutter", Origin::Sdk), ("http", Origin::Hosted)]);
    found.unseen_workspace = true;
    assert_eq!(gap(&found, "flutter"), Some(GapName::LocalPackage));
    assert_eq!(gap(&found, "http"), Some(GapName::LocalPackage));
}

#[test]
fn an_unread_map_adds_no_gap_because_its_whole_scope_gap_holds() {
    assert_eq!(gap(&PackageMap::default(), "anything"), None);
}

#[test]
fn the_origin_of_each_dependency_form() {
    assert_eq!(origin(&[("sdk", Some("flutter"))]), Origin::Sdk);
    assert_eq!(
        origin(&[
            ("hosted", Some("https://pub.dev")),
            ("version", Some("^1.0.0"))
        ]),
        Origin::Hosted
    );
    assert_eq!(
        origin(&[("git", Some("https://github.com/a/b.git"))]),
        Origin::RemoteGit
    );
    for local in [
        origin(&[("path", Some("../other"))]),
        origin(&[("git", Some("../other"))]),
        origin(&[("git", None)]),
        origin(&[("version", Some("1.0.0")), ("other", None)]),
    ] {
        assert!(matches!(local, Origin::Local(_)), "{local:?}");
    }
    assert!(remote("git@github.com:a/b.git"));
    assert!(!remote("/home/me/b"));
    assert!(!remote("file:///home/me/b"));
}
