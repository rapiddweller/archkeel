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
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
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
const DEPENDENCY_SECTIONS: [(&str, Kind); 5] = [
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
    /// Each declared dependency, in the order of the sections and of the names.
    pub declared: Vec<Declared>,
    /// What the reader does not know in the dependency tables: each one makes the crate UNKNOWN.
    pub unknown: Vec<String>,
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

/// The line of a dependency in the text of its manifest, and the text of the line. The line of
/// the key in its section, else the line of the header `[<section>.<key>]`, else the first line.
pub fn line_of(text: &str, kind: Kind, key: &str) -> (i64, String) {
    let sections: Vec<&str> = DEPENDENCY_SECTIONS
        .iter()
        .filter(|(_, own)| *own == kind)
        .map(|(section, _)| *section)
        .collect();
    let quoted = format!("\"{key}\"");
    let mut inside = false;
    let mut found = None;
    for (index, line) in text.lines().enumerate() {
        let line = line.trim();
        if line.starts_with('[') {
            inside = sections.iter().any(|section| {
                let header = line.trim_matches(|c| c == '[' || c == ']');
                header == *section || header.ends_with(&format!(".{section}"))
            });
            let table = sections.iter().any(|section| {
                line.ends_with(&format!("{section}.{key}]"))
                    || line.ends_with(&format!("{section}.{quoted}]"))
            });
            if table {
                return (to_line(index), line.to_owned());
            }
        } else if inside
            && [key, quoted.as_str()]
                .iter()
                .any(|name| starts_with_key(line, name))
        {
            found.get_or_insert((to_line(index), line.to_owned()));
        }
    }
    found.unwrap_or((1, text.lines().next().unwrap_or("").trim().to_owned()))
}

fn starts_with_key(line: &str, key: &str) -> bool {
    line.strip_prefix(key)
        .is_some_and(|rest| rest.trim_start().starts_with(['=', '.']))
}

fn to_line(index: usize) -> i64 {
    i64::try_from(index + 1).unwrap_or(i64::MAX)
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
