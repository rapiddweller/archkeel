// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package gaps of the survey (AD-454): each file or `pubspec.yaml` key that can make a
//! `package:` URI name a file that the root `pubspec.yaml` alone does not give.
//!
//! A bounded YAML parse finds keys, not words in scalar values. An unreadable form keeps a gap.

use archkeel_facts::envelope::Input;
use archkeel_snapshot::Snapshot;
use saphyr::{LoadableYamlNode, Yaml};

use super::index::Index;
use super::names::{GapName, Gaps, Place};
use super::package_map::{self, Origin, PackageMap};
use super::workspace;
use crate::discover::{pubspec_path, Discovery, PACKAGE_FILES};
use crate::module::is_identifier;

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

/// The origin of each dependency of a root `pubspec.yaml`; an override replaces the dependency.
/// `None` for a document that the survey does not read key by key.
pub(super) fn declared(document: &Yaml<'_>) -> Option<std::collections::BTreeMap<String, Origin>> {
    let mut found = std::collections::BTreeMap::new();
    for section in ["dependencies", "dev_dependencies", "dependency_overrides"] {
        let Some(deps) = document.as_mapping_get(section) else {
            continue;
        };
        if deps.is_null() {
            continue;
        }
        for (name, dependency) in deps.as_mapping()? {
            let name = name.as_str().filter(|name| is_identifier(name))?;
            let origin = origin(dependency)?;
            found.insert(name.to_owned(), origin);
        }
    }
    Some(found)
}

/// The package keys and the marker for an unreadable document.
#[derive(Debug, Default, PartialEq, Eq)]
pub(super) struct PubspecWords {
    pub(super) workspace: bool,
    pub(super) resolution: bool,
    pub(super) path: bool,
    pub(super) escape: bool,
}

/// Parse one bounded YAML document. Other documents retain a conservative gap.
pub(super) fn yaml(text: &str) -> Option<Yaml<'_>> {
    if !text.contains('\\')
        && text.len() <= 65_536
        && text
            .lines()
            .all(|line| line.len() - line.trim_start().len() <= 128)
        && text
            .bytes()
            .filter(|byte| matches!(byte, b'[' | b'{' | b'-' | b':' | b'?'))
            .count()
            <= 128
    {
        if let Ok(mut documents) = Yaml::load_from_str(text) {
            if documents.len() == 1 {
                return documents.pop();
            }
        }
    }
    None
}

pub(super) fn keys(text: &str) -> PubspecWords {
    if let Some(document) = yaml(text) {
        let mut found = PubspecWords::default();
        if yaml_keys(&document, &mut found, 0) {
            return found;
        }
    }
    let mut found = words(text);
    found.escape = true;
    found
}

pub(super) fn yaml_keys(node: &Yaml<'_>, found: &mut PubspecWords, depth: usize) -> bool {
    if depth > 128 {
        return false;
    }
    match node {
        Yaml::Mapping(map) => map.iter().all(|(key, value)| {
            let Some(key) = key.as_str() else {
                return false;
            };
            if depth == 0
                && matches!(
                    key,
                    "dependencies" | "dev_dependencies" | "dependency_overrides"
                )
            {
                let Some(deps) = value.as_mapping() else {
                    return false;
                };
                return deps.iter().all(|(name, dependency)| {
                    name.as_str().is_some() && yaml_keys(dependency, found, depth + 2)
                });
            }
            match key {
                "path" => found.path = true,
                "workspace" => found.workspace = true,
                "resolution" => {
                    found.workspace = true;
                    found.resolution = true;
                }
                "<<" => return false,
                _ => {}
            }
            yaml_keys(value, found, depth + 1)
        }),
        Yaml::Sequence(items) => items.iter().all(|item| yaml_keys(item, found, depth + 1)),
        Yaml::Value(_) => true,
        _ => false,
    }
}

fn words(text: &str) -> PubspecWords {
    let mut found = PubspecWords {
        escape: text.contains('\\'),
        ..PubspecWords::default()
    };
    for line in text.split(['\n', '\r']) {
        if line.trim_start_matches([' ', '\t']).starts_with('#') {
            continue;
        }
        for word in line.split(|c: char| !c.is_ascii_alphanumeric()) {
            match word {
                "path" => found.path = true,
                "workspace" => found.workspace = true,
                "resolution" => {
                    found.workspace = true;
                    found.resolution = true;
                }
                _ => {}
            }
        }
    }
    found
}

/// The origin of one dependency value: a version text or null is hosted; a mapping states it.
fn origin(dependency: &Yaml<'_>) -> Option<Origin> {
    match dependency {
        Yaml::Value(_) => Some(Origin::Hosted),
        Yaml::Mapping(keys) => {
            let mut pairs = Vec::new();
            for (key, value) in keys {
                let key = key.as_str()?;
                let text = if key == "git" && value.is_mapping() {
                    value.as_mapping_get("url").and_then(Yaml::as_str)
                } else {
                    value.as_str()
                };
                pairs.push((key, text));
            }
            Some(package_map::origin(&pairs))
        }
        _ => None,
    }
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
