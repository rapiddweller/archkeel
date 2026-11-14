// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The crates below the scan roots and the file that starts each module tree.
//!
//! The collector reads each `Cargo.toml` itself. It never starts `cargo`: a collector has no
//! child process and no network (AD-316). `cargo metadata` is the oracle of the tests instead.

use std::collections::BTreeMap;
use std::rc::Rc;

use crate::manifest::{self, ident, Manifest, Target, TargetKind};
use crate::manifest_lines::LineIndex;
use crate::paths::normalize;
use crate::redirects::{self, Redirect};
use crate::source::read_text;
use crate::toml::{self, Table};
use archkeel_snapshot::paths::{dirname, join};
use archkeel_snapshot::Snapshot;

/// One manifest, read once: its table and its text.
pub(crate) struct Parsed {
    pub(crate) table: Table,
    text: String,
    dir: String,
}

/// A place that the scan cannot read: the file (or none) and the reason.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Problem {
    pub reason: String,
    pub file: String,
}

/// The file that starts one module tree of a crate.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Root {
    pub module: String,
    pub rel: String,
    /// A `tests/`, `benches/` or `examples/` target: Cargo builds it for tests only. A build
    /// script stays production scope.
    pub test: bool,
}

pub(crate) struct Crate {
    pub ident: String,
    /// The directory of the manifest, relative to the snapshot.
    pub dir: String,
    pub manifest: Manifest,
    /// The text of `Cargo.toml`, read once, and the line of each dependency in it.
    pub text: String,
    pub lines: LineIndex,
    pub roots: Vec<Root>,
    /// The module and file that other crates reach: the library, else the main binary.
    pub primary: Option<Root>,
    pub registry: crate::registry::Registry,
}

pub(crate) struct Workspace {
    pub crates: Vec<Crate>,
    pub problems: Vec<Problem>,
    /// The primary root of each crate by name; the first crate of a name wins.
    primaries: BTreeMap<String, Option<Root>>,
}

/// Find the crates among `files`, all the files below the scan roots.
pub(crate) fn discover(source: &mut Snapshot, files: &[String], namespace: &str) -> Workspace {
    let mut found = Workspace {
        crates: Vec::new(),
        problems: Vec::new(),
        primaries: BTreeMap::new(),
    };
    let mut tables: BTreeMap<String, Option<Rc<Parsed>>> = BTreeMap::new();
    for file in files.iter().filter(|file| is_manifest(file)) {
        let dir = dirname(file).to_owned();
        match manifest_table(source, &mut tables, &dir) {
            Err(reason) => found.problems.push(Problem {
                reason,
                file: file.clone(),
            }),
            Ok(None) => {}
            Ok(Some(parsed)) => {
                found.member(source, &mut tables, (&dir, &parsed), files, namespace);
            }
        }
    }
    found
        .crates
        .sort_by(|a, b| a.manifest.package.cmp(&b.manifest.package));
    found.duplicates();
    for krate in &found.crates {
        found
            .primaries
            .entry(krate.ident.clone())
            .or_insert_with(|| krate.primary.clone());
    }
    found
}

fn is_manifest(file: &str) -> bool {
    file == "Cargo.toml" || file.ends_with("/Cargo.toml")
}

/// The manifest of `dir`, read and parsed once; `Ok(None)` when the directory has none.
pub(crate) fn manifest_table(
    source: &mut Snapshot,
    tables: &mut BTreeMap<String, Option<Rc<Parsed>>>,
    dir: &str,
) -> Result<Option<Rc<Parsed>>, String> {
    if let Some(known) = tables.get(dir) {
        return Ok(known.clone());
    }
    let rel = join(dir, "Cargo.toml");
    let table = if source.is_file(&rel) {
        let text = read_text(source, &rel)?;
        let table = toml::parse(&text).map_err(|error| format!("Cannot read {rel}: {error}"))?;
        Some(Rc::new(Parsed {
            table,
            text,
            dir: dir.to_owned(),
        }))
    } else {
        None
    };
    tables.insert(dir.to_owned(), table.clone());
    Ok(table)
}

/// The nearest workspace manifest at or above `dir`.
fn workspace_manifest(
    source: &mut Snapshot,
    tables: &mut BTreeMap<String, Option<Rc<Parsed>>>,
    dir: &str,
) -> Option<Rc<Parsed>> {
    let mut at = dir.to_owned();
    loop {
        if let Ok(Some(parsed)) = manifest_table(source, tables, &at) {
            if manifest::is_workspace(&parsed.table) {
                return Some(parsed);
            }
        }
        if at.is_empty() {
            return None;
        }
        at = dirname(&at).to_owned();
    }
}

impl Workspace {
    /// The module and file that other crates reach in the crate `package`, when it is in the
    /// workspace and has a library or a main binary.
    pub(crate) fn primary_of(&self, package: &str) -> Option<&Root> {
        self.primaries.get(package)?.as_ref()
    }

    /// Add the package of one manifest, with the edition and the dependencies of its workspace.
    fn member(
        &mut self,
        source: &mut Snapshot,
        tables: &mut BTreeMap<String, Option<Rc<Parsed>>>,
        (dir, parsed): (&str, &Parsed),
        files: &[String],
        namespace: &str,
    ) {
        let above = workspace_manifest(source, tables, dir);
        let dependencies = above
            .as_ref()
            .map(|above| manifest::workspace_dependencies(&above.table))
            .unwrap_or_default();
        let Some(mut read) = manifest::read(&parsed.table, &dependencies) else {
            return;
        };
        // A registry name is no crate of the workspace unless a place that can redirect it says so
        // or cannot be read (`redirects`): then the old rule (a name of the workspace is an edge)
        // stays, and an unread place is a gap.
        if !read.remote.is_empty() {
            let place = (dir, &parsed.table);
            match redirects::of(source, tables, place, above.as_deref()) {
                Redirect::None => {}
                Redirect::Possible => read.remote.clear(),
                Redirect::Unread(reason) => {
                    read.remote.clear();
                    self.problems.push(Problem {
                        reason,
                        file: join(dir, "Cargo.toml"),
                    });
                }
            }
        }
        if read.edition.is_none() {
            read.edition = above
                .as_ref()
                .and_then(|above| manifest::workspace_edition(&above.table));
        }
        let registry = crate::registry::read(
            source,
            (dir, &parsed.table),
            above.as_ref().map(|p| (p.dir.as_str(), &p.table)),
            &read,
        );
        self.add(dir, read, registry, &parsed.text, files, namespace);
    }

    fn add(
        &mut self,
        dir: &str,
        manifest: Manifest,
        registry: crate::registry::Registry,
        text: &str,
        files: &[String],
        namespace: &str,
    ) {
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
        self.missing_roots(&manifest, dir, files);
        let mut targets = declared(&manifest, dir, files);
        // A target inside the crate directory is the owner of its file; a shared one comes last.
        targets.sort_by_key(|(_, rel)| (!within(dir, rel), rel.clone()));
        let mut roots = Vec::new();
        let mut primary = None;
        let has_lib = targets
            .iter()
            .any(|(target, _)| target.kind == TargetKind::Lib);
        for (target, rel) in targets {
            let main = target.kind == TargetKind::Lib
                || (!has_lib && target.kind == TargetKind::Bin && target.name == manifest.package);
            let name = if main {
                package.clone()
            } else {
                secondary(&package, &target)
            };
            let root = Root {
                module: format!("{namespace}.{name}"),
                rel,
                test: target.kind.is_test(),
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
            text: text.to_owned(),
            lines: LineIndex::new(text),
            roots,
            primary,
            registry,
        });
    }

    /// A path that the manifest names and the listing does not hold: the file is missing, or the
    /// walk skipped its directory (build output). Either way its facts are missing: a gap.
    fn missing_roots(&mut self, manifest: &Manifest, dir: &str, files: &[String]) {
        let build = manifest.build.iter().flatten();
        let named = manifest
            .lib_path
            .iter()
            .chain(manifest.bins.iter().map(|bin| &bin.path))
            .chain(manifest.extra.iter().map(|target| &target.path))
            .chain(build);
        for path in named {
            let Some(rel) = normalize(&join(dir, path)).filter(|rel| !files.contains(rel)) else {
                continue;
            };
            let reason =
                format!("The manifest names a source file that the scan did not list: {rel}");
            self.problems.push(Problem {
                reason,
                file: join(dir, "Cargo.toml"),
            });
        }
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
    pub(crate) fn holds(&self, root: &Root) -> bool {
        self.contains(&root.rel)
    }

    /// Whether a file is in the directory of this crate.
    pub(crate) fn contains(&self, rel: &str) -> bool {
        within(&self.dir, rel)
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
        TargetKind::Build => format!("{package}.build_script"),
        kind => format!("{package}.{}_{name}", kind.word()),
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
        kind: TargetKind::Lib,
        name: manifest.package.clone(),
        path: lib,
    });
    targets.extend(manifest.bins.iter().cloned());
    targets.extend(manifest.extra.iter().cloned());
    targets.push(Target {
        kind: TargetKind::Bin,
        name: manifest.package.clone(),
        path: "src/main.rs".to_owned(),
    });
    for (kind, folder) in [
        (TargetKind::Bin, "src/bin"),
        (TargetKind::Test, "tests"),
        (TargetKind::Example, "examples"),
        (TargetKind::Bench, "benches"),
    ] {
        targets.extend(discovered(kind, folder, &join(dir, folder), files));
    }
    match &manifest.build {
        Some(Some(path)) => targets.push(Target {
            kind: TargetKind::Build,
            name: "build".to_owned(),
            path: path.clone(),
        }),
        Some(None) => targets.push(Target {
            kind: TargetKind::Build,
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

/// The targets that Cargo finds in `folder`: `folder/name.rs` and `folder/name/main.rs`.
fn discovered(kind: TargetKind, folder: &str, below: &str, files: &[String]) -> Vec<Target> {
    let prefix = format!("{below}/");
    let mut found = Vec::new();
    for file in files {
        let Some(rest) = file.strip_prefix(&prefix) else {
            continue;
        };
        let name = match rest.split('/').collect::<Vec<_>>()[..] {
            [leaf] => leaf.strip_suffix(".rs"),
            [name, "main.rs"] => Some(name),
            _ => None,
        };
        if let Some(name) = name {
            let path = rest.to_owned();
            found.push(Target {
                kind,
                name: name.to_owned(),
                path: format!("{folder}/{path}"),
            });
        }
    }
    found
}

#[cfg(test)]
#[path = "crates_tests.rs"]
mod tests;
