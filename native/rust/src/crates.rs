// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The crates below the scan roots and the file that starts each module tree.
//!
//! The collector reads each `Cargo.toml` itself. It never starts `cargo`: a collector has no
//! child process and no network (AD-316). `cargo metadata` is the oracle of the tests instead.

use std::collections::BTreeMap;

use crate::manifest::{self, ident, Manifest, Target};
use crate::paths::normalize;
use crate::source::read_text;
use crate::toml::{self, Table};
use archkeel_snapshot::paths::{dirname, join};
use archkeel_snapshot::Snapshot;

/// A place that the scan cannot read: the file (or none) and the reason.
#[derive(Clone, Debug, PartialEq)]
pub struct Problem {
    pub reason: String,
    pub file: String,
}

/// The file that starts one module tree of a crate.
#[derive(Clone, Debug, PartialEq)]
pub struct Root {
    pub module: String,
    pub rel: String,
    /// A `tests/`, `benches/` or `examples/` target: Cargo builds it for tests only. A build
    /// script stays production scope.
    pub test: bool,
}

pub struct Crate {
    pub ident: String,
    /// The directory of the manifest, relative to the snapshot.
    pub dir: String,
    pub manifest: Manifest,
    pub roots: Vec<Root>,
    /// The module and file that other crates reach: the library, else the main binary.
    pub primary: Option<Root>,
}

pub struct Workspace {
    pub crates: Vec<Crate>,
    pub problems: Vec<Problem>,
}

/// Find the crates among `files`, all the files below the scan roots.
pub fn discover(source: &mut Snapshot, files: &[String], namespace: &str) -> Workspace {
    let mut found = Workspace {
        crates: Vec::new(),
        problems: Vec::new(),
    };
    let mut tables: BTreeMap<String, Option<Table>> = BTreeMap::new();
    for file in files.iter().filter(|file| is_manifest(file)) {
        let dir = dirname(file).to_owned();
        match manifest_table(source, &mut tables, &dir) {
            Err(reason) => found.problems.push(Problem {
                reason,
                file: file.clone(),
            }),
            Ok(None) => {}
            Ok(Some(table)) => {
                let workspace = workspace_table(source, &mut tables, &dir);
                if let Some(read) = manifest::read(&table, &workspace) {
                    found.add(&dir, read, files, namespace);
                }
            }
        }
    }
    found
        .crates
        .sort_by(|a, b| a.manifest.package.cmp(&b.manifest.package));
    found.duplicates();
    found
}

fn is_manifest(file: &str) -> bool {
    file == "Cargo.toml" || file.ends_with("/Cargo.toml")
}

/// The parsed manifest of `dir`; `Ok(None)` when the directory has none.
fn manifest_table(
    source: &mut Snapshot,
    tables: &mut BTreeMap<String, Option<Table>>,
    dir: &str,
) -> Result<Option<Table>, String> {
    if let Some(known) = tables.get(dir) {
        return Ok(known.clone());
    }
    let rel = join(dir, "Cargo.toml");
    let table = if source.is_file(&rel) {
        let text = read_text(source, &rel)?;
        Some(toml::parse(&text).map_err(|error| format!("Cannot read {rel}: {error}"))?)
    } else {
        None
    };
    tables.insert(dir.to_owned(), table.clone());
    Ok(table)
}

/// The `[workspace.dependencies]` of the nearest workspace manifest above `dir`.
fn workspace_table(
    source: &mut Snapshot,
    tables: &mut BTreeMap<String, Option<Table>>,
    dir: &str,
) -> Table {
    let mut at = dir.to_owned();
    loop {
        if let Ok(Some(table)) = manifest_table(source, tables, &at) {
            if manifest::is_workspace(&table) {
                return manifest::workspace_dependencies(&table);
            }
        }
        if at.is_empty() {
            return Table::new();
        }
        at = dirname(&at).to_owned();
    }
}

impl Workspace {
    fn add(&mut self, dir: &str, manifest: Manifest, files: &[String], namespace: &str) {
        if let Some(name) = &manifest.lib_name {
            let reason = format!(
                "The library name {name} differs from the package name {}: a path to it is not read",
                manifest.package
            );
            self.problems.push(Problem {
                reason,
                file: join(dir, "Cargo.toml"),
            });
        }
        for reason in &manifest.unknown {
            self.problems.push(Problem {
                reason: format!("{reason} in {}", manifest.package),
                file: join(dir, "Cargo.toml"),
            });
        }
        let package = ident(&manifest.package);
        let mut targets = declared(&manifest, dir, files);
        // A target inside the crate directory is the owner of its file; a shared one comes last.
        targets.sort_by_key(|(_, rel)| (!within(dir, rel), rel.clone()));
        let mut roots = Vec::new();
        let mut primary = None;
        let has_lib = targets.iter().any(|(target, _)| target.kind == "lib");
        for (target, rel) in targets {
            let main = target.kind == "lib"
                || (!has_lib && target.kind == "bin" && target.name == manifest.package);
            let name = if main {
                package.clone()
            } else {
                secondary(&package, &target)
            };
            let root = Root {
                module: format!("{namespace}.{name}"),
                rel,
                test: matches!(target.kind, "test" | "bench" | "example"),
            };
            if main {
                primary = Some(root.clone());
            }
            roots.push(root);
        }
        self.crates.push(Crate {
            ident: package,
            dir: dir.to_owned(),
            manifest,
            roots,
            primary,
        });
    }

    fn duplicates(&mut self) {
        for pair in self.crates.windows(2) {
            if pair[0].ident == pair[1].ident {
                let reason = format!("Two crates have the name {}", pair[0].ident);
                self.problems.push(Problem {
                    reason,
                    file: String::new(),
                });
            }
        }
    }
}

fn within(dir: &str, rel: &str) -> bool {
    archkeel_snapshot::paths::within(if dir.is_empty() { "." } else { dir }, rel)
}

impl Crate {
    /// Whether a root file is in the directory of this crate.
    pub fn holds(&self, root: &Root) -> bool {
        within(&self.dir, &root.rel)
    }
}

/// The module name of a target that is not the main one: `crate.bin_tool`, `crate.build_script`.
fn secondary(package: &str, target: &Target) -> String {
    let name: String = target
        .name
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '_' })
        .collect();
    match target.kind {
        "build" => format!("{package}.build_script"),
        kind => format!("{package}.{kind}_{name}"),
    }
}

/// The targets that the manifest names and the files that Cargo finds by its conventions,
/// each with its path relative to the snapshot. A target whose file is missing is left out;
/// the missing file is a gap in the walk, not here.
fn declared(manifest: &Manifest, dir: &str, files: &[String]) -> Vec<(Target, String)> {
    let mut targets: Vec<Target> = Vec::new();
    let lib = manifest
        .lib_path
        .clone()
        .unwrap_or_else(|| "src/lib.rs".to_owned());
    targets.push(Target {
        kind: "lib",
        name: manifest.package.clone(),
        path: lib,
    });
    targets.extend(manifest.bins.iter().cloned());
    targets.push(Target {
        kind: "bin",
        name: manifest.package.clone(),
        path: "src/main.rs".to_owned(),
    });
    for (kind, folder) in [
        ("bin", "src/bin"),
        ("test", "tests"),
        ("example", "examples"),
        ("bench", "benches"),
    ] {
        let prefix = join(dir, folder) + "/";
        for file in files {
            let Some(name) = file
                .strip_prefix(&prefix)
                .and_then(|n| n.strip_suffix(".rs"))
            else {
                continue;
            };
            if !name.contains('/') {
                targets.push(Target {
                    kind,
                    name: name.to_owned(),
                    path: format!("{folder}/{name}.rs"),
                });
            }
        }
    }
    match &manifest.build {
        Some(Some(path)) => targets.push(Target {
            kind: "build",
            name: "build".to_owned(),
            path: path.clone(),
        }),
        Some(None) => targets.push(Target {
            kind: "build",
            name: "build".to_owned(),
            path: "build.rs".to_owned(),
        }),
        None => {}
    }
    let mut seen = Vec::new();
    let mut resolved = Vec::new();
    for target in targets {
        let Some(rel) = normalize(&join(dir, &target.path)) else {
            continue;
        };
        if files.contains(&rel) && !seen.contains(&rel) {
            seen.push(rel.clone());
            resolved.push((target, rel));
        }
    }
    resolved
}

#[cfg(test)]
#[path = "crates_tests.rs"]
mod tests;
