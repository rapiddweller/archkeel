// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package gaps of the survey (AD-454): each file or `pubspec.yaml` key that can make a
//! `package:` URI name a file that the root `pubspec.yaml` alone does not give.
//!
//! A bounded YAML parse finds keys, not words in scalar values. An unreadable form keeps a gap.

use archkeel_facts::envelope::{Input, Role};
use archkeel_facts::identity::sha256_hex;
use archkeel_snapshot::Snapshot;
use saphyr::{LoadableYamlNode, Yaml};

use super::index::Index;
use super::names::{GapName, Gaps, Place};
use super::package_map::{self, Origin, PackageMap};
use crate::discover::{Discovery, PACKAGE_FILES};
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
    if discovery.pubspec_digest.is_some() {
        if let Some(raw) = snapshot.read(PUBSPEC) {
            map = pubspec_gaps(&raw, snapshot, (discovery, roots, index), gaps, &mut inputs);
        }
    }
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
    for rel in files.iter().filter(|rel| rel.as_str() != PUBSPEC) {
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
fn declared(document: &Yaml<'_>) -> Option<std::collections::BTreeMap<String, Origin>> {
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
struct PubspecWords {
    workspace: bool,
    resolution: bool,
    path: bool,
    escape: bool,
}

/// Parse one bounded YAML document. Other documents retain a conservative gap.
fn yaml(text: &str) -> Option<Yaml<'_>> {
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

fn keys(text: &str) -> PubspecWords {
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

fn yaml_keys(node: &Yaml<'_>, found: &mut PubspecWords, depth: usize) -> bool {
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

/// The member names of the workspace that the root `pubspec.yaml` declares, or `None` when the
/// survey cannot read it. An import of a member is a gap at the import (AD-800).
fn workspace(
    text: &str,
    snapshot: &mut Snapshot,
    own: &str,
    roots: &[String],
    index: &Index<'_>,
    inputs: &mut Vec<Input>,
) -> Option<std::collections::BTreeSet<String>> {
    if text.contains(['&', '*', '!', '\\']) || index.syntax.iter().any(Option::is_none) {
        return None;
    }
    if snapshot.is_file("pubspec.lock")
        || Snapshot::is_link(snapshot, "pubspec.lock")
        || snapshot.is_file(".dart_tool/package_config.json")
        || Snapshot::is_link(snapshot, ".dart_tool/package_config.json")
    {
        return None;
    }
    let document = yaml(text)?;
    if document.as_mapping_get("dependency_overrides").is_some() {
        return None;
    }
    let members = document
        .as_mapping_get("workspace")
        .and_then(Yaml::as_sequence)?;
    if members.len() > 32 || own.is_empty() {
        return None;
    }
    let mut names = std::collections::BTreeSet::from([own.to_owned()]);
    let mut read = Vec::new();
    for member in members {
        let dir = member.as_str().filter(|s| is_identifier(s))?;
        if roots
            .iter()
            .any(|root| root == "." || root.split('/').next() == Some(dir))
            || Snapshot::is_link(snapshot, dir)
            || snapshot.is_file(&format!("{dir}/pubspec_overrides.yaml"))
            || Snapshot::is_link(snapshot, &format!("{dir}/pubspec_overrides.yaml"))
        {
            return None;
        }
        let path = format!("{dir}/pubspec.yaml");
        if Snapshot::is_link(snapshot, &path) {
            return None;
        }
        let raw = snapshot.read(&path)?;
        let Ok(member_text) = std::str::from_utf8(&raw) else {
            return None;
        };
        if member_text.contains(['&', '*', '!', '\\']) {
            return None;
        }
        let doc = yaml(member_text)?;
        let name = doc
            .as_mapping_get("name")
            .and_then(Yaml::as_str)
            .filter(|s| is_identifier(s))?;
        if !names.insert(name.to_owned()) || !member_safe(&doc) {
            return None;
        }
        read.push(Input {
            digest: sha256_hex(&raw),
            path,
            role: Role::Resolution,
        });
    }
    inputs.extend(read);
    names.remove(own);
    Some(names)
}

fn member_safe(doc: &Yaml<'_>) -> bool {
    let Some(map) = doc.as_mapping() else {
        return false;
    };
    for (key, value) in map {
        let Some(key) = key.as_str() else {
            return false;
        };
        if matches!(key, "workspace" | "dependency_overrides") {
            return false;
        }
        if key == "resolution" {
            if value.as_str() != Some("workspace") {
                return false;
            }
            continue;
        }
        let mut found = PubspecWords::default();
        if matches!(key, "dependencies" | "dev_dependencies") {
            let Some(deps) = value.as_mapping() else {
                return false;
            };
            if !deps
                .iter()
                .all(|(name, value)| name.as_str().is_some() && yaml_keys(value, &mut found, 0))
            {
                return false;
            }
        } else if !yaml_keys(value, &mut found, 0) {
            return false;
        }
        if found.path || found.workspace {
            return false;
        }
    }
    true
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
    if let Some(value) = document.as_mapping_get("resolution") {
        if value.as_str() == Some("workspace") {
            map.unseen_workspace = true;
        } else {
            gaps.named(GapName::Workspace, Place::File(PUBSPEC), message);
        }
    }
    if document.as_mapping_get("workspace").is_some() {
        let own = &discovery.package_name;
        match workspace(text, snapshot, own, roots, index, inputs) {
            Some(members) => map.members = members,
            None => gaps.named(GapName::Workspace, Place::File(PUBSPEC), message),
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
