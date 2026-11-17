// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The workspaces of a Dart package (AD-542, AD-800): the workspace that the package
//! `pubspec.yaml` declares, and the workspace root above a member package (#1539).

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::envelope::{Input, Role};
use archkeel_facts::identity::sha256_hex;
use archkeel_snapshot::paths::{normpath, within};
use archkeel_snapshot::Snapshot;
use saphyr::Yaml;

use super::index::Index;
use super::package_map::Origin;
use super::pubspec_keys::{declared, keys, yaml, yaml_keys, PubspecWords};
use crate::discover::{pubspec_path, Discovery};
use crate::module::is_identifier;

/// The most members of a workspace above the package that the survey reads.
const MEMBERS: usize = 128;

/// The member names of the workspace that the root `pubspec.yaml` declares, or `None` when the
/// survey cannot read it. An import of a member is a gap at the import (AD-800).
pub(super) fn workspace(
    text: &str,
    snapshot: &mut Snapshot,
    own: &str,
    roots: &[String],
    index: &Index<'_>,
    inputs: &mut Vec<Input>,
) -> Option<BTreeSet<String>> {
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
    if Vec::len(members) > 32 || str::is_empty(own) {
        return None;
    }
    let mut names = BTreeSet::from([own.to_owned()]);
    let mut read = Vec::new();
    for member in members {
        let dir = Yaml::as_str(member).filter(|s| is_identifier(s))?;
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
        let Some(key) = Yaml::as_str(key) else {
            return false;
        };
        if matches!(key, "workspace" | "dependency_overrides") {
            return false;
        }
        if key == "resolution" {
            if Yaml::as_str(value) != Some("workspace") {
                return false;
            }
            continue;
        }
        let mut found = PubspecWords::default();
        if matches!(key, "dependencies" | "dev_dependencies") {
            let Some(deps) = value.as_mapping() else {
                return false;
            };
            if !deps.iter().all(|(name, value)| {
                Yaml::as_str(name).is_some() && yaml_keys(value, &mut found, 0)
            }) {
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

/// The workspace above the package directory that lists the package (#1539).
pub(super) struct Above {
    /// The directory of the workspace root, empty for the snapshot root.
    pub(super) root: String,
    /// The names of the other packages of the workspace, the root package too.
    pub(super) members: BTreeSet<String>,
    /// The names that a member declares with a local origin.
    pub(super) local: BTreeSet<String>,
    /// The overrides of the workspace root, which apply to each member.
    pub(super) overrides: BTreeMap<String, Origin>,
}

/// One readable `pubspec.yaml` of a workspace: its text, digest and document. `None` for a link,
/// a missing file or a form that the survey does not read key by key.
fn readable(snapshot: &mut Snapshot, path: &str, inputs: &mut Vec<Input>) -> Option<String> {
    if Snapshot::is_link(snapshot, path) {
        return None;
    }
    let raw = snapshot.read(path)?;
    let text = std::str::from_utf8(&raw).ok()?.to_owned();
    let words = keys(&text);
    if words.escape || text.contains(['&', '*', '!']) {
        return None;
    }
    inputs.push(Input {
        digest: sha256_hex(&raw),
        path: path.to_owned(),
        role: Role::Resolution,
    });
    Some(text)
}

/// The workspace root of a member package below the snapshot root: the nearest directory above
/// the package with a `pubspec.yaml`, which must list the package in `workspace:`. Each member
/// `pubspec.yaml` must be readable, and no member directory may hold a scan root. `None` when the
/// survey cannot read the workspace: then each import of a package is a gap.
pub(super) fn above(
    snapshot: &mut Snapshot,
    discovery: &Discovery,
    roots: &[String],
    inputs: &mut Vec<Input>,
) -> Option<Above> {
    let dir = String::as_str(&discovery.package_dir);
    let parts: Vec<&str> = dir.split('/').filter(|part| !str::is_empty(part)).collect();
    let root = (0..Vec::len(&parts))
        .rev()
        .map(|end| parts[..end].join("/"))
        .find(|candidate| snapshot.is_file(&pubspec_path(candidate)))?;
    let mut read = Vec::new();
    let text = readable(snapshot, &pubspec_path(&root), &mut read)?;
    let document = yaml(&text)?;
    let listed = document.as_mapping_get("workspace")?.as_sequence()?;
    if Vec::len(listed) > MEMBERS {
        return None;
    }
    let prefix = if String::is_empty(&root) {
        String::new()
    } else {
        format!("{root}/")
    };
    let mut found = Above {
        root,
        members: BTreeSet::from([Yaml::as_str(document.as_mapping_get("name")?)?.to_owned()]),
        local: BTreeSet::new(),
        overrides: root_overrides(&document)?,
    };
    let mut own = false;
    for entry in listed {
        let member = normpath(&format!("{prefix}{}", Yaml::as_str(entry)?));
        if member == dir {
            own = true;
        } else {
            let (name, local) = member_package(snapshot, &member, roots, &mut read)?;
            found.members.insert(name);
            found.local.extend(local);
        }
    }
    found.members.remove(&discovery.package_name);
    inputs.extend(read);
    own.then_some(found)
}

/// The name of one other member of a workspace and the names that it declares with a local
/// origin. `None` when the member holds a scan root, has its own overrides file or is not read.
fn member_package(
    snapshot: &mut Snapshot,
    member: &str,
    roots: &[String],
    read: &mut Vec<Input>,
) -> Option<(String, Vec<String>)> {
    let overrides = format!("{member}/pubspec_overrides.yaml");
    if roots.iter().any(|scan| within(member, scan))
        || snapshot.is_file(&overrides)
        || Snapshot::is_link(snapshot, &overrides)
    {
        return None;
    }
    let text = readable(snapshot, &pubspec_path(member), read)?;
    let document = yaml(&text)?;
    let name = Yaml::as_str(document.as_mapping_get("name")?).filter(|s| is_identifier(s))?;
    let local = declared(&document)?
        .into_iter()
        .filter(|(_, origin)| matches!(origin, Origin::Local(_)))
        .map(|(dependency, _)| dependency)
        .collect();
    Some((name.to_owned(), local))
}

/// The overrides of a workspace root: they apply to each member.
fn root_overrides(document: &Yaml<'_>) -> Option<BTreeMap<String, Origin>> {
    let Some(overrides) = document.as_mapping_get("dependency_overrides") else {
        return Some(BTreeMap::new());
    };
    let declared = declared(document)?;
    Some(
        declared
            .into_iter()
            .filter(|(name, _)| overrides.as_mapping_get(name).is_some())
            .collect(),
    )
}
