// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Cargo settings of the repository that can build a registry crate from other code than the
//! identity that `Cargo.lock` records (AD-774, #1518). The scan reads each `.cargo/config.toml` and
//! `.cargo/config` at any level of the repository and the `[patch]` and `[replace]` tables of the
//! manifests. A replacement of the crates.io source and `paths` overrides can change any registry
//! crate; a patch or a replace changes the crate that it names. Each such crate loses the identity
//! proof of the bounded library models (AD-424), and the file and line are named.
//!
//! Settings outside the repository (`$CARGO_HOME`, the environment, `--config`) are not read: the
//! result does not depend on the machine, and the stated premise of the scan covers them.

use std::collections::BTreeMap;

use crate::source::{read_text, BUILD_MARKERS};
use crate::toml::{self, Table, Value};
use archkeel_snapshot::paths::join;
use archkeel_snapshot::{Entry, Snapshot};

const CONFIGS: [&str; 2] = ["config.toml", "config"];
/// Directories that hold no Cargo setting of the work tree: the Git store and installed packages.
const SKIPPED: [&str; 2] = [".git", "node_modules"];
const MAX_DEPTH: usize = 128;
const MAX_ENTRIES: usize = 1_000_000;

/// A setting that withholds an identity proof: its file, its line (0 when no line applies), the
/// text of the line, and what it is.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Cited {
    pub rel: String,
    pub line: i64,
    pub excerpt: String,
    pub what: String,
}

/// The registry crates whose code a setting of the repository can change.
#[derive(Clone, Debug, Default)]
pub(crate) struct Overrides {
    /// A setting that changes every registry crate.
    pub all: Option<Cited>,
    /// A setting that changes one registry crate, by its package name.
    pub packages: BTreeMap<String, Cited>,
}

impl Overrides {
    /// The setting that changes the package `name`, if any.
    pub(crate) fn of(&self, name: &str) -> Option<&Cited> {
        self.packages.get(name).or(self.all.as_ref())
    }

    fn every(&mut self, cited: Cited) {
        self.all.get_or_insert(cited);
    }

    fn one(&mut self, name: &str, cited: Cited) {
        self.packages.entry(name.to_owned()).or_insert(cited);
    }
}

/// The Cargo configurations of the whole repository. A directory that cannot be listed, a link
/// to a directory, or a walk over the limits may hide a configuration: every crate is changed.
pub(crate) fn configs(snapshot: &mut Snapshot) -> Overrides {
    let mut found = Overrides::default();
    let mut pending = vec![(String::new(), 0_usize)];
    let mut remaining = MAX_ENTRIES;
    let hidden = |dir: &str, why: &str| Cited {
        rel: dir.to_owned(),
        line: 0,
        excerpt: String::new(),
        what: format!("A directory that may hold a Cargo configuration {why}"),
    };
    while let Some((dir, depth)) = pending.pop() {
        let Some(entries) = Snapshot::listing(snapshot, &dir) else {
            found.every(hidden(&dir, "cannot be listed"));
            continue;
        };
        if depth > MAX_DEPTH || Vec::len(&entries) > remaining {
            found.every(hidden(&dir, "is beyond the limits of the walk"));
            break;
        }
        remaining -= Vec::len(&entries);
        // Build output is not source, and a parallel build changes it while the scan runs.
        let built = entries.iter().any(|(name, kind)| {
            *kind == Entry::File && BUILD_MARKERS.contains(&String::as_str(name))
        });
        for (name, kind) in entries {
            let rel = join(&dir, &name);
            match kind {
                Entry::Directory if name == ".cargo" => config_dir(snapshot, &rel, &mut found),
                // A link named `.cargo` may lead to a configuration outside the repository.
                Entry::Link { .. } if name == ".cargo" => found.every(hidden(&rel, "is a link")),
                Entry::Directory if !built && !SKIPPED.contains(&String::as_str(&name)) => {
                    pending.push((rel, depth + 1));
                }
                Entry::Link { to_directory: true } if !built => {
                    found.every(hidden(&rel, "is a link"));
                }
                _ => (),
            }
        }
    }
    found
}

fn config_dir(snapshot: &mut Snapshot, dir: &str, found: &mut Overrides) {
    for name in CONFIGS {
        let rel = join(dir, name);
        if !snapshot.is_file(&rel) {
            continue;
        }
        let read = read_text(snapshot, &rel).and_then(|text| Ok((toml::parse(&text)?, text)));
        match read {
            Ok((table, text)) => config(&table, &Lines::new(&rel, &text), found),
            Err(_) => found.every(Cited {
                rel: rel.clone(),
                line: 1,
                excerpt: String::new(),
                what: "A Cargo configuration that the scan cannot read".to_owned(),
            }),
        }
    }
}

/// The settings of one Cargo configuration.
fn config(table: &Table, lines: &Lines<'_>, found: &mut Overrides) {
    let sources = table.get("source").and_then(Value::table);
    if sources.and_then(|s| s.get("crates-io")).is_some() {
        found.every(lines.cite(
            "source.crates-io",
            "replace-with",
            "A replacement of crates.io",
        ));
    }
    if matches!(table.get("paths"), Some(Value::Array(paths)) if !Vec::is_empty(paths)) {
        found.every(lines.cite("", "paths", "A paths override"));
    }
    patches(table, lines, found);
}

/// The `[patch]` and `[replace]` tables of a manifest.
pub(crate) fn manifest(table: &Table, lines: &Lines<'_>, found: &mut Overrides) {
    patches(table, lines, found);
    for key in table
        .get("replace")
        .and_then(Value::table)
        .into_iter()
        .flatten()
        .map(|e| e.0)
    {
        match package_of_spec(key) {
            Some(name) => found.one(name, lines.cite("replace", key, "A replace")),
            None => found.every(lines.cite("replace", key, "A replace")),
        }
    }
}

fn patches(table: &Table, lines: &Lines<'_>, found: &mut Overrides) {
    let registries = table
        .get("patch")
        .and_then(Value::table)
        .into_iter()
        .flatten();
    for (registry, entries) in registries {
        let header = format!("patch.{registry}");
        for (key, value) in entries.table().into_iter().flatten() {
            let renamed = value
                .table()
                .and_then(|t| t.get("package"))
                .and_then(Value::text);
            let name = renamed.unwrap_or(key);
            found.one(name, lines.cite(&header, key, "A patch"));
        }
    }
}

/// The package name of a package ID spec (`name`, `name:1.0`, `name@1.0`, `url#name@1.0`).
fn package_of_spec(spec: &str) -> Option<&str> {
    let tail = spec.rsplit_once('#').map_or(spec, |(_, tail)| tail);
    let name = tail.split([':', '@']).next()?;
    let plain = !str::is_empty(name)
        && name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
        && !name.starts_with(|c: char| c.is_ascii_digit());
    plain.then_some(name)
}

/// The lines of one Cargo file, to cite a setting. The line is evidence only: a key that the
/// pass cannot find gives the line of its table, else the first line.
pub(crate) struct Lines<'a> {
    rel: &'a str,
    text: &'a str,
}

impl<'a> Lines<'a> {
    pub(crate) fn new(rel: &'a str, text: &'a str) -> Self {
        Self { rel, text }
    }

    fn cite(&self, header: &str, key: &str, what: &str) -> Cited {
        let (line, excerpt) = self.find(header, key);
        Cited {
            rel: self.rel.to_owned(),
            line,
            excerpt,
            what: what.to_owned(),
        }
    }

    fn find(&self, header: &str, key: &str) -> (i64, String) {
        let plain = |s: &str| s.replace(['"', '\'', ' '], "");
        let wanted = plain(header);
        let sub = plain(&format!("{header}.{key}"));
        let sub = sub.trim_start_matches('.');
        let assigned = format!("{}=", plain(key));
        let dotted = format!("{sub}=");
        let mut inside = str::is_empty(header);
        let mut table_line = None;
        for (number, line) in self.text.lines().enumerate() {
            let text = plain(line.trim());
            let table = text
                .strip_prefix('[')
                .map(|name| name.trim_end_matches(']'));
            inside = table.map_or(inside, |name| name == wanted);
            let cited = (
                i64::try_from(number + 1).unwrap_or(i64::MAX),
                line.trim().to_owned(),
            );
            if inside && table.is_some() && table_line.is_none() {
                table_line = Some(cited.clone());
            }
            let hit = match table {
                Some(name) => name == sub,
                None => (inside && text.starts_with(&assigned)) || text.starts_with(&dotted),
            };
            if hit {
                return cited;
            }
        }
        let first = (1, self.text.lines().next().unwrap_or("").trim().to_owned());
        table_line.unwrap_or(first)
    }
}

#[cfg(test)]
#[path = "registry_overrides_tests.rs"]
mod tests;
