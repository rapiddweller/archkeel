// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Lock facts for bounded library models, not a Cargo resolver. Missing, stale or ambiguous
//! facts give no proof. Source overrides and non-registry dependencies give no proof either.

use crate::manifest::{self, Manifest};
use crate::source::read_text;
use crate::toml::{self, Table, Value};
use archkeel_snapshot::paths::{dirname, join};
use archkeel_snapshot::Snapshot;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Default)]
pub(crate) struct Registry {
    pub direct: BTreeSet<String>,
    pub packages: BTreeMap<String, Locked>,
}

#[derive(Clone, Debug)]
pub(crate) struct Locked {
    pub version: String,
    pub dependencies: BTreeSet<String>,
}

fn text<'a>(table: &'a Table, key: &str) -> Option<&'a str> {
    table.get(key)?.text()
}

fn dependencies(table: &Table) -> BTreeSet<String> {
    match table.get("dependencies") {
        Some(Value::Array(values)) => values
            .iter()
            .filter_map(Value::text)
            .filter_map(|s| s.split_whitespace().next())
            .map(str::to_owned)
            .collect(),
        _ => BTreeSet::new(),
    }
}

fn packages(tables: &[Value]) -> BTreeMap<String, Locked> {
    let mut seen = BTreeSet::new();
    let mut duplicate = BTreeSet::new();
    let mut found = BTreeMap::new();
    for table in tables.iter().filter_map(Value::table) {
        let Some(name) = text(table, "name") else {
            continue;
        };
        if !seen.insert(name) {
            duplicate.insert(name);
        }
        let source = text(table, "source");
        let checksum = text(table, "checksum").unwrap_or("");
        if source != Some("registry+https://github.com/rust-lang/crates.io-index")
            || checksum.len() != 64
            || !checksum.bytes().all(|b| b.is_ascii_hexdigit())
        {
            continue;
        }
        if let Some(version) = text(table, "version") {
            found.insert(
                name.to_owned(),
                Locked {
                    version: version.to_owned(),
                    dependencies: dependencies(table),
                },
            );
        }
    }
    found.retain(|name, _| !duplicate.contains(name.as_str()));
    found
}

fn version_matches(requirement: &str, locked: &str) -> bool {
    if let Some(exact) = requirement.strip_prefix('=') {
        return exact == locked;
    }
    let requirement = requirement.strip_prefix('^').unwrap_or(requirement);
    let parse = |s: &str| {
        s.split('.')
            .map(|part| part.parse::<u64>().ok().filter(|n| n.to_string() == part))
            .collect::<Option<Vec<_>>>()
    };
    let (Some(wanted), Some(actual)) = (parse(requirement), parse(locked)) else {
        return false;
    };
    !wanted.is_empty()
        && wanted.len() <= 3
        && actual.len() == 3
        && wanted[0] > 0
        && wanted[0] == actual[0]
        && wanted
            .iter()
            .zip(&actual)
            .find(|(a, b)| a != b)
            .is_none_or(|(a, b)| a < b)
}

fn requirement(value: &Value) -> Option<&str> {
    match value {
        Value::Text(version) => Some(version),
        Value::Table(table)
            if !table.contains_key("path")
                && !table.contains_key("git")
                && !table.contains_key("registry") =>
        {
            text(table, "version")
        }
        _ => None,
    }
}

fn entry<'a>(value: &'a Value, inherited: Option<&'a Value>) -> Option<&'a Value> {
    let Some(table) = value.table() else {
        return Some(value);
    };
    match table.get("workspace") {
        Some(Value::Boolean(true))
            if !["path", "git", "registry", "version", "package"]
                .iter()
                .any(|key| table.contains_key(*key)) =>
        {
            inherited
        }
        Some(_) => None,
        None => Some(value),
    }
}

/// A source replacement can retain a registry spelling in Cargo.lock. Do not model such builds.
fn overrides(snapshot: &mut Snapshot, root: &str) -> bool {
    let mut at = root;
    loop {
        if [".cargo/config", ".cargo/config.toml"]
            .iter()
            .any(|p| snapshot.is_file(&join(at, p)))
        {
            return true;
        }
        if at.is_empty() {
            return false;
        }
        at = dirname(at);
    }
}

pub(crate) fn read(
    snapshot: &mut Snapshot,
    member: (&str, &Table),
    workspace: Option<(&str, &Table)>,
    manifest: &Manifest,
) -> Registry {
    let (root, table) = workspace.unwrap_or(member);
    let rejected = |t: &Table| t.contains_key("patch") || t.contains_key("replace");
    if rejected(table) || rejected(member.1) || overrides(snapshot, root) {
        return Registry::default();
    }
    let lock_path = join(root, "Cargo.lock");
    if !snapshot.is_file(&lock_path) {
        return Registry::default();
    }
    let lock = read_text(snapshot, &lock_path)
        .ok()
        .and_then(|s| toml::parse(&s).ok());
    if !matches!(
        lock.as_ref().and_then(|t| t.get("version")),
        Some(Value::Integer(3 | 4))
    ) {
        return Registry::default();
    }
    let Some(Value::Array(tables)) = lock.as_ref().and_then(|t| t.get("package")) else {
        return Registry::default();
    };
    let parent: Vec<_> = tables
        .iter()
        .filter_map(Value::table)
        .filter(|t| text(t, "name") == Some(&manifest.package) && !t.contains_key("source"))
        .collect();
    let [parent] = parent.as_slice() else {
        return Registry::default();
    };
    let version = manifest::get(member.1, &["package", "version"]);
    let inherited_version =
        manifest::get(table, &["workspace", "package", "version"]).and_then(Value::text);
    let version = match version {
        Some(Value::Text(version)) => Some(version.as_str()),
        Some(Value::Table(value)) if value.get("workspace") == Some(&Value::Boolean(true)) => {
            inherited_version
        }
        _ => None,
    };
    if version.is_none() || version != text(parent, "version") {
        return Registry::default();
    }
    let reachable = dependencies(parent);
    let packages = packages(tables);
    let inherited = manifest::workspace_dependencies(table);
    let mut direct = BTreeSet::new();
    let mut rejected_keys = BTreeSet::new();
    for (key, value, _) in manifest::dependency_entries(member.1) {
        let Some(package) = manifest.dependencies.get(&manifest::ident(key)) else {
            continue;
        };
        let proven = entry(value, inherited.get(key))
            .and_then(requirement)
            .zip(packages.get(package))
            .is_some_and(|(requirement, locked)| {
                reachable.contains(package) && version_matches(requirement, &locked.version)
            });
        if proven {
            direct.insert(manifest::ident(key));
        } else {
            rejected_keys.insert(manifest::ident(key));
        }
    }
    direct.retain(|key| !rejected_keys.contains(key));
    Registry { direct, packages }
}
