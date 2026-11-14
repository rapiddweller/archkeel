// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The selected files of a scan, as `explore_scope.selected_paths` finds them.
//!
//! `Path.rglob("*.py")` yields each entry whose name ends with `.py`, a directory too, and enters
//! each directory that is not a symlink. A file under `__pycache__`, a file that resolves outside
//! the snapshot and, when the scope leaves tests out, a test source (as written or as resolved)
//! is not selected. The order is the order of the path parts.
//!
//! What the walk cannot see soundly is an `Unseen` value, never a silent omission (AD-367): the
//! survey writes a gap for each one, so the scope that holds it cannot be PASS.

use std::collections::HashSet;

use archkeel_snapshot::paths::join;
use archkeel_snapshot::{Hidden, Snapshot};

/// A file or directory that the native walk cannot read soundly.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Unseen {
    /// A selected symlink to a missing file. Python selects it too, and its read fails with
    /// `FileNotFoundError`; the survey writes that failure.
    Missing(String),
    /// A name that is not UTF-8. Python selects the file or walks the directory; the native
    /// collector writes a collection gap that names the path.
    NotUtf8(String),
    /// A selected file over `MAX_FILE_BYTES`, which the snapshot does not read (AD-319).
    Oversized(String),
    /// A selected FIFO, socket or device. Python selects it and its read can block until the
    /// timeout; the native collector never reads it and writes a collection gap that names it.
    Special(String),
}

impl Unseen {
    /// The reason of the collection gap; `None` for `Missing`, whose gap is a parse failure.
    pub(crate) fn reason(&self, snapshot: &Snapshot) -> Option<String> {
        match self {
            Unseen::Missing(_) => None,
            Unseen::NotUtf8(path) => Some(format!("Source name is not UTF-8: {path}")),
            Unseen::Oversized(path) => snapshot.size_gap(path),
            Unseen::Special(path) => Some(format!("Source is not a regular file: {path}")),
        }
    }
}

/// The selected files of the roots, sorted by their parts, and what the walk cannot see.
pub(crate) struct Scope {
    pub selected: Vec<String>,
    pub unseen: Vec<Unseen>,
    /// The stub and compiled module files below the roots: the survey cannot read them as
    /// source, and Python can import them (AD-450).
    pub foreign: Vec<String>,
    /// The linked directories below the roots: Python follows them, the walk does not (AD-450).
    pub linked: Vec<String>,
}

/// The suffixes of a module file that the survey does not read: stubs, compiled modules and
/// `.pyw` sources, which Python imports and the survey does not select (AD-450).
const FOREIGN: [&str; 5] = [".pyi", ".so", ".pyd", ".pyc", ".pyw"];

/// The scope of the roots: the selected files and the unseen entries.
pub(crate) fn scope(snapshot: &mut Snapshot, roots: &[String], exclude_tests: bool) -> Scope {
    let mut found = Vec::new();
    let mut unseen = Vec::new();
    let mut foreign = Vec::new();
    let mut linked = Vec::new();
    for root in roots {
        if !snapshot.is_dir(root) {
            continue;
        }
        let mut pending = vec![root.trim_end_matches('/').to_owned()];
        while let Some(directory) = pending.pop() {
            let (files, directories) = snapshot.entries(&directory);
            let names = files.iter().chain(directories.iter());
            for name in names {
                place(join(&directory, name), &mut found, &mut foreign);
            }
            let children = directories.iter().map(|name| join(&directory, name));
            let (links, plain): (Vec<String>, Vec<String>) =
                children.partition(|child| snapshot.is_link(child));
            linked.extend(links);
            pending.extend(plain);
            hidden(snapshot, &directory, exclude_tests, &mut unseen);
        }
    }
    found.retain(|rel| keep(snapshot, rel, exclude_tests));
    found.extend(unseen.iter().filter_map(|item| match item {
        Unseen::Missing(rel) => Some(rel.clone()),
        _ => None,
    }));
    found.sort_by(|left, right| left.split('/').cmp(right.split('/')));
    found.dedup();
    foreign.retain(|rel| keep(snapshot, rel, exclude_tests));
    // AD-472: a stub beside its selected source module is no runtime module. Python imports the
    // `.py`, and a gap of that file holds the run when it does not read or parse.
    let sources: HashSet<&str> = found.iter().map(String::as_str).collect();
    foreign.retain(|rel| {
        !rel.strip_suffix('i')
            .is_some_and(|source| rel.ends_with(".pyi") && sources.contains(source))
    });
    foreign.sort();
    linked.retain(|rel| !in_cache(rel) && !(exclude_tests && is_test_source(rel)));
    linked.sort();
    Scope {
        selected: found,
        unseen,
        foreign,
        linked,
    }
}

/// Put a listed path into the source files or the stub and compiled module files.
fn place(rel: String, found: &mut Vec<String>, foreign: &mut Vec<String>) {
    if rel.ends_with(".py") {
        found.push(rel);
    } else if FOREIGN.iter().any(|suffix| rel.ends_with(suffix)) {
        foreign.push(rel);
    }
}

/// The entries of `directory` that `Snapshot::entries` leaves out. A dangling `*.py` link is
/// selected, as `Path.rglob` and `_inside` select it.
fn hidden(snapshot: &mut Snapshot, directory: &str, exclude_tests: bool, out: &mut Vec<Unseen>) {
    for entry in snapshot.hidden_entries(directory) {
        let item = match entry {
            Hidden::Dangling(name) if name.ends_with(".py") => {
                let rel = join(directory, &name);
                if in_cache(&rel) || exclude_tests && is_test_source(&rel) {
                    continue;
                }
                Unseen::Missing(rel)
            }
            Hidden::Special(name) if name.ends_with(".py") => {
                let rel = join(directory, &name);
                if !keep(snapshot, &rel, exclude_tests) {
                    continue;
                }
                Unseen::Special(rel)
            }
            Hidden::NotUtf8 {
                name,
                directory: is_dir,
            } if is_dir || name.ends_with(".py") => Unseen::NotUtf8(join(directory, &name)),
            _ => continue,
        };
        out.push(item);
    }
}

/// The selected files that the snapshot refused for their size. Call it after the inputs read;
/// each one must become a gap, so the result must be used. The survey finds them as it reads
/// (`survey::unread`); the scope dump and its tests use this.
#[cfg(any(feature = "dump", test))]
#[must_use]
pub(crate) fn oversized(snapshot: &Snapshot, selected: &[String]) -> Vec<Unseen> {
    selected
        .iter()
        .filter(|rel| snapshot.size_gap(rel).is_some())
        .map(|rel| Unseen::Oversized(rel.clone()))
        .collect()
}

/// `"__pycache__" in path.parts`: Python never selects a file there.
fn in_cache(rel: &str) -> bool {
    rel.split('/').any(|part| part == "__pycache__")
}

fn keep(snapshot: &mut Snapshot, rel: &str, exclude_tests: bool) -> bool {
    if in_cache(rel) {
        return false;
    }
    let Some(real) = snapshot.real(rel) else {
        return false;
    };
    !(exclude_tests && (is_test_source(rel) || is_test_source(&real)))
}

/// `profiles.is_test_source` for Python: a part `test`, `tests` or `__tests__` above the file, or
/// a name `test_*.py` or `*_test.py`.
pub(crate) fn is_test_source(path: &str) -> bool {
    let mut parts = path
        .rsplit('/')
        .filter(|part| !part.is_empty() && *part != ".");
    let name = parts.next().unwrap_or_default();
    let test_name =
        (name.starts_with("test_") && name.ends_with(".py")) || name.ends_with("_test.py");
    test_name || parts.any(|part| ["test", "tests", "__tests__"].contains(&part))
}

#[cfg(test)]
#[path = "discover_tests.rs"]
mod tests;
