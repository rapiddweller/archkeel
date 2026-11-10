// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the collector reads from one `Cargo.toml`: the package name, the files that start a
//! module tree, the names that source can use for a crate, and the declared features.
//!
//! This is a fact about declared dependencies. The collector does not read a dependency as an
//! edge: only a path in source is an edge (AD-335).

use std::collections::{BTreeMap, BTreeSet};

use crate::toml::{Table, Value};

/// The sections that declare a dependency.
const DEPENDENCY_SECTIONS: [&str; 3] = ["dependencies", "dev-dependencies", "build-dependencies"];

/// The name of a crate as source writes it: `-` becomes `_`.
pub fn ident(name: &str) -> String {
    name.replace('-', "_")
}

/// The target of one module tree, as the manifest declares it or Cargo finds it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Target {
    pub kind: &'static str,
    pub name: String,
    /// Relative to the directory of the manifest.
    pub path: String,
}

#[derive(Clone, Debug)]
pub struct Manifest {
    pub package: String,
    /// The `[lib] name` when it differs from the package name; source uses this name.
    pub lib_name: Option<String>,
    pub lib_path: Option<String>,
    pub bins: Vec<Target>,
    /// `None` when `build = false`; the path of the script when the key is a string.
    pub build: Option<Option<String>>,
    /// The name that source writes, and the package it stands for.
    pub dependencies: BTreeMap<String, String>,
    pub features: BTreeSet<String>,
}

pub(crate) fn get<'a>(table: &'a Table, path: &[&str]) -> Option<&'a Value> {
    let (last, parents) = path.split_last()?;
    let mut table = table;
    for key in parents {
        table = table.get(*key)?.table()?;
    }
    table.get(*last)
}

fn text<'a>(table: &'a Table, path: &[&str]) -> Option<&'a str> {
    get(table, path)?.text()
}

/// The `[workspace.dependencies]` table of a workspace manifest, empty when there is none.
pub fn workspace_dependencies(table: &Table) -> Table {
    get(table, &["workspace", "dependencies"])
        .and_then(Value::table)
        .cloned()
        .unwrap_or_default()
}

pub fn is_workspace(table: &Table) -> bool {
    table.contains_key("workspace")
}

/// The package of a manifest, or `None` for a virtual workspace.
pub fn read(table: &Table, workspace: &Table) -> Option<Manifest> {
    let package = text(table, &["package", "name"])?.to_owned();
    let lib_name = text(table, &["lib", "name"])
        .filter(|name| *name != package && *name != ident(&package))
        .map(str::to_owned);
    let mut dependencies = BTreeMap::new();
    for (name, value) in dependency_entries(table) {
        dependencies.insert(ident(name), package_of(name, value, workspace));
    }
    let mut features: BTreeSet<String> = get(table, &["features"])
        .and_then(Value::table)
        .map(|features| features.keys().cloned().collect())
        .unwrap_or_default();
    features.extend(dependencies.keys().cloned());
    Some(Manifest {
        lib_name,
        lib_path: text(table, &["lib", "path"]).map(str::to_owned),
        bins: bins(table, &package),
        build: build(table),
        package,
        dependencies,
        features,
    })
}

fn build(table: &Table) -> Option<Option<String>> {
    match get(table, &["package", "build"]) {
        Some(Value::Text(path)) => Some(Some(path.clone())),
        Some(Value::Other) => None,
        _ => Some(None),
    }
}

fn bins(table: &Table, package: &str) -> Vec<Target> {
    let Some(Value::Array(items)) = get(table, &["bin"]) else {
        return Vec::new();
    };
    items
        .iter()
        .filter_map(Value::table)
        .filter_map(|bin| {
            let name = bin.get("name")?.text()?.to_owned();
            let path = match bin.get("path").and_then(Value::text) {
                Some(path) => path.to_owned(),
                None if name == package => "src/main.rs".to_owned(),
                None => format!("src/bin/{name}.rs"),
            };
            Some(Target {
                kind: "bin",
                name,
                path,
            })
        })
        .collect()
}

/// Each entry of each dependency section, also below `[target.<name>.<section>]`.
fn dependency_entries(table: &Table) -> Vec<(&String, &Value)> {
    let mut sections: Vec<&Table> = DEPENDENCY_SECTIONS
        .iter()
        .filter_map(|name| table.get(*name)?.table())
        .collect();
    if let Some(targets) = table.get("target").and_then(Value::table) {
        for target in targets.values().filter_map(Value::table) {
            sections.extend(
                DEPENDENCY_SECTIONS
                    .iter()
                    .filter_map(|name| target.get(*name)?.table()),
            );
        }
    }
    sections.into_iter().flatten().collect()
}

/// The package behind a dependency name: `package = "x"` renames it, and `workspace = true`
/// reads the entry of the workspace.
fn package_of(name: &str, value: &Value, workspace: &Table) -> String {
    let own = value.table();
    let inherited = own
        .filter(|entry| entry.contains_key("workspace"))
        .and_then(|_| workspace.get(name))
        .and_then(Value::table);
    [own, inherited]
        .into_iter()
        .flatten()
        .find_map(|entry| entry.get("package")?.text())
        .map_or_else(|| ident(name), ident)
}

#[cfg(test)]
#[path = "manifest_tests.rs"]
mod tests;
