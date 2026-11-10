// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the collector reads from one `Cargo.toml`: the package name, the files that start a
//! module tree, the names that source can use for a crate, and the declared features.
//!
//! A dependency that the manifest declares is a crate edge itself (AD-335, amendment of
//! 2026-11-10): a crate can use another crate only if its manifest declares it, so the declared
//! dependency is a sound over-approximation of what source uses, also when source hides the use
//! in a macro or a generated token. A table or a form that this reader does not know is UNKNOWN.

use std::collections::{BTreeMap, BTreeSet};

use crate::toml::{Table, Value};

/// Which build of the crate a dependency belongs to.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Kind {
    Normal,
    Dev,
    Build,
}

impl Kind {
    /// The name of the section as Cargo writes it.
    pub fn section(self) -> &'static str {
        match self {
            Kind::Normal => "dependencies",
            Kind::Dev => "dev-dependencies",
            Kind::Build => "build-dependencies",
        }
    }
}

/// The sections that declare a dependency. Cargo still reads the underscore forms of the dev and
/// the build section (deprecated, edition 2021 and before).
pub(crate) const DEPENDENCY_SECTIONS: [(&str, Kind); 5] = [
    ("dependencies", Kind::Normal),
    ("dev-dependencies", Kind::Dev),
    ("dev_dependencies", Kind::Dev),
    ("build-dependencies", Kind::Build),
    ("build_dependencies", Kind::Build),
];

/// One dependency of one manifest: the key as written, the package it stands for and its kind.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Declared {
    pub key: String,
    pub package: String,
    pub kind: Kind,
}

/// The name of a crate as source writes it: `-` becomes `_`.
pub fn ident(name: &str) -> String {
    name.replace('-', "_")
}

/// What Cargo builds from a target.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TargetKind {
    Lib,
    Bin,
    Test,
    Example,
    Bench,
    Build,
}

impl TargetKind {
    /// The word in a module name, as Cargo writes it.
    pub fn word(self) -> &'static str {
        match self {
            Self::Lib => "lib",
            Self::Bin => "bin",
            Self::Test => "test",
            Self::Example => "example",
            Self::Bench => "bench",
            Self::Build => "build",
        }
    }

    /// Cargo builds `tests/`, `benches/` and `examples/` targets for tests only.
    pub fn is_test(self) -> bool {
        matches!(self, Self::Test | Self::Bench | Self::Example)
    }
}

/// The target of one module tree, as the manifest declares it or Cargo finds it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Target {
    pub kind: TargetKind,
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
    /// Each declared dependency, in the order of the sections and of the names.
    pub declared: Vec<Declared>,
    /// What the reader does not know in the dependency tables: each one makes the crate UNKNOWN.
    pub unknown: Vec<String>,
    pub features: BTreeSet<String>,
    /// `package.edition`; `None` for `edition.workspace = true` until the workspace gives it.
    pub edition: Option<String>,
}

impl Manifest {
    /// Edition 2015, also when the manifest names no edition or one that is not known: a `use`
    /// path or a `::` path starts at the crate root there.
    pub fn legacy(&self) -> bool {
        !matches!(self.edition.as_deref(), Some("2018" | "2021" | "2024"))
    }
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

/// `[workspace.package] edition` of a workspace manifest.
pub fn workspace_edition(table: &Table) -> Option<String> {
    text(table, &["workspace", "package", "edition"]).map(str::to_owned)
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
    let mut declared = Vec::new();
    let mut unknown = unknown_tables(table);
    for (name, value, kind) in dependency_entries(table) {
        if !matches!(value, Value::Text(_) | Value::Table(_)) {
            unknown.push(format!(
                "A dependency has a form that the reader does not know: {name}"
            ));
        }
        let package = package_of(name, value, workspace);
        dependencies.insert(ident(name), package.clone());
        declared.push(Declared {
            key: name.clone(),
            package,
            kind,
        });
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
        declared,
        unknown,
        features,
        edition: text(table, &["package", "edition"]).map(str::to_owned),
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
                kind: TargetKind::Bin,
                name,
                path,
            })
        })
        .collect()
}

/// Each entry of each dependency section, also below `[target.<name>.<section>]`.
fn dependency_entries(table: &Table) -> Vec<(&String, &Value, Kind)> {
    let mut tables: Vec<&Table> = vec![table];
    if let Some(targets) = table.get("target").and_then(Value::table) {
        tables.extend(targets.values().filter_map(Value::table));
    }
    let mut found = Vec::new();
    for scope in tables {
        for (section, kind) in DEPENDENCY_SECTIONS {
            if let Some(entries) = scope.get(section).and_then(Value::table) {
                found.extend(entries.iter().map(|(name, value)| (name, value, kind)));
            }
        }
    }
    found
}

/// A key that looks like a dependency table and is none that Cargo reads. The reader never skips
/// it: a crate that holds one is UNKNOWN.
fn unknown_tables(table: &Table) -> Vec<String> {
    let known = |key: &str| {
        DEPENDENCY_SECTIONS
            .iter()
            .any(|(section, _)| *section == key)
    };
    let like = |key: &str| (key.contains("depend") || key.contains("deps")) && !known(key);
    let mut found: Vec<String> = table
        .keys()
        .filter(|key| like(key))
        .map(|key| format!("A dependency table that the reader does not know: [{key}]"))
        .collect();
    if let Some(targets) = table.get("target").and_then(Value::table) {
        for (name, scope) in targets {
            let keys = scope.table().into_iter().flat_map(Table::keys);
            found.extend(keys.filter(|key| like(key)).map(|key| {
                format!("A dependency table that the reader does not know: [target.{name}.{key}]")
            }));
        }
    }
    found
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
