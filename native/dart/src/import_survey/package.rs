// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package gaps of the survey (AD-454): each file or `pubspec.yaml` key that can make a
//! `package:` URI name a file that the root `pubspec.yaml` alone does not give.
//!
//! A bounded YAML parse finds keys, not words in scalar values. An unreadable form keeps a gap.

use archkeel_facts::envelope::Input;
use archkeel_snapshot::Snapshot;

use super::index::Index;
use super::names::{GapName, Gaps, Place};
use super::package_map::PackageMap;
use super::pubspec_keys::{declared, keys, yaml, PubspecWords};
use super::workspace;
use crate::discover::{pubspec_path, Discovery, PACKAGE_FILES};

const PUBSPEC: &str = "pubspec.yaml";

/// Add the package gaps of `discovery`, of the snapshot root and of each directory above a scan
/// root to `gaps`, and return the inputs and the package map (AD-800). A package file above a
/// scan root can own the files below it, as the root `pubspec.yaml` owns `lib`.
/// `.dart_tool/package_config.json` keeps its own check (`config.rs`, AD-454).
pub(crate) fn package_gaps(
    snapshot: &mut Snapshot,
    discovery: &Discovery,
    roots: &[String],
    index: &Index<'_>,
    gaps: &mut Gaps,
) -> (Vec<Input>, PackageMap) {
    let mut inputs = Vec::new();
    let mut map = PackageMap::default();
    let own = pubspec_path(&discovery.package_dir);
    if discovery.pubspec_digest.is_some() {
        if let Some(raw) = snapshot.read(&own) {
            map = pubspec_gaps(&raw, snapshot, (discovery, roots, index), gaps, &mut inputs);
        }
    }
    let workspace_root = map.workspace_root.as_deref().map(pubspec_path);
    let mut files: Vec<String> = discovery.package_files.clone();
    let above = roots.iter().flat_map(|root| {
        let parts: Vec<&str> = root.split('/').collect();
        (1..parts.len()).map(move |end| parts[..end].join("/"))
    });
    let dirs: Vec<String> = std::iter::once(String::new()).chain(above).collect();
    for dir in dirs
        .iter()
        .filter(|dir| !matches!(dir.as_str(), "." | ".."))
    {
        for name in PACKAGE_FILES {
            let rel = if dir.is_empty() {
                name.to_owned()
            } else {
                format!("{dir}/{name}")
            };
            if snapshot.is_file(&rel) || Snapshot::is_link(snapshot, &rel) {
                files.push(rel);
            }
        }
    }
    files.sort();
    files.dedup();
    let read = |rel: &&String| **rel != own && Some(rel.as_str()) != workspace_root.as_deref();
    for rel in files.iter().filter(read) {
        if rel.rsplit('/').next() == Some(PUBSPEC) {
            let message = "a second package holds or is in a scan root; its URIs are not resolved";
            gaps.named(GapName::NestedPackage, Place::File(rel), message);
        } else {
            let message = "this file can map a package to another directory; it is not read";
            gaps.named(GapName::PackageConfig, Place::File(rel), message);
        }
    }
    (inputs, map)
}

/// The gaps of the keys of the root `pubspec.yaml` and its package map (AD-800). Bytes that are
/// not UTF-8 already give the SDK gap of the discovery. A document that the survey does not read
/// key by key keeps the whole-scope gaps of its words.
fn pubspec_gaps(
    raw: &[u8],
    snapshot: &mut Snapshot,
    (discovery, roots, index): (&Discovery, &[String], &Index<'_>),
    gaps: &mut Gaps,
    inputs: &mut Vec<Input>,
) -> PackageMap {
    let Ok(text) = std::str::from_utf8(raw) else {
        return PackageMap::default();
    };
    let found = keys(text);
    let document = yaml(text).filter(|_| !found.escape && !text.contains(['&', '*', '!']));
    let declared = document.as_ref().and_then(declared);
    let (Some(document), Some(declared)) = (document, declared) else {
        word_gaps(&found, gaps);
        return PackageMap::default();
    };
    let mut map = PackageMap {
        read: true,
        declared,
        ..PackageMap::default()
    };
    let message = "the package is a workspace or a member of one; its packages are not resolved";
    let own = pubspec_path(&discovery.package_dir);
    if let Some(value) = document.as_mapping_get("resolution") {
        if value.as_str() != Some("workspace") {
            gaps.named(GapName::Workspace, Place::File(&own), message);
        } else if let Some(seen) = workspace::above(snapshot, discovery, roots, inputs) {
            map.members = seen.members;
            map.local_names = seen.local;
            map.declared.extend(seen.overrides);
            map.workspace_root = Some(seen.root);
        } else {
            map.unseen_workspace = true;
        }
    }
    if document.as_mapping_get("workspace").is_some() {
        let name = &discovery.package_name;
        match workspace::workspace(text, snapshot, name, roots, index, inputs) {
            Some(members) => map.members = members,
            None => gaps.named(GapName::Workspace, Place::File(&own), message),
        }
    }
    map
}

/// The whole-scope gaps of a root `pubspec.yaml` that the survey reads only word by word.
fn word_gaps(found: &PubspecWords, gaps: &mut Gaps) {
    if found.workspace {
        let message =
            "the package is a workspace or a member of one; its packages are not resolved";
        gaps.named(GapName::Workspace, Place::File(PUBSPEC), message);
    }
    if found.path {
        let message = "a dependency has a local path; that package is outside the survey";
        gaps.named(GapName::PathDependency, Place::File(PUBSPEC), message);
    }
    if found.escape && !found.path {
        let message = "the pubspec is not fully read; it can hide a local path key";
        gaps.named(GapName::PathDependency, Place::File(PUBSPEC), message);
    }
}

#[cfg(test)]
#[path = "package_tests.rs"]
mod tests;
