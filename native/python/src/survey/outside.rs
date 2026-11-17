// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the repository outside the scan that can write a module of the scan (#1522,
//! AD-770). Such a write changes a route: `app.lib.f = secret` in a script makes
//! `from app.lib import f` give a private function.
//!
//! The walk reads the snapshot outside the scan modules. It does not enter `.git`, a symbolic
//! link, `__pycache__`, `node_modules`, a directory with a `CACHEDIR.TAG` (build output, AD-432) or
//! a `pyvenv.cfg` (installed packages). A test file (`is_test_source`) is not read: the stated
//! premise of the run covers test code, as it covers code outside the repository.
//!
//! - A Python file is read with the escape rule of AD-504 (`uses.rs`): a use of a module of the scan
//!   other than a load or call of an attribute escapes that module. A literal import call of a
//!   module of the scan escapes it and the packages above it.
//! - A hazard site of a Python file (AD-450) can give a module object by its name. Each module of
//!   the scan that a string of the file names then escapes (`outside_sites.rs`). Two forms are
//!   proven harmless: an import call whose name cannot name a module of the scan, and `exec`,
//!   `eval` or `compile` of a literal text without a name.
//! - A Python file that Python cannot run (it does not decode or parse at Python 3.14) writes
//!   nothing. A file over the size limit, or with a declared encoding that is not UTF-8, can run:
//!   it is read as the text of an extension.
//! - An extension source (C, C++, Cython, a Rust file with the C API of Python) or a compiled
//!   module escapes each module of the scan that a dotted word of its text names
//!   (`outside_native.rs`).
//!
//! An escaped module withholds its routes and its names (AD-504, AD-550): the rules that read them
//! are UNKNOWN with the gap of the unproven publication route. A write that the repository does not
//! show (a name built at run time, code outside the repository) is the stated premise of the run.

use std::collections::{HashMap, HashSet};

use archkeel_facts::pyminor::PyMinor;
use archkeel_snapshot::paths::join;
use archkeel_snapshot::{Entry, Snapshot};

use super::binders::Binders;
use super::imports;
use super::lazy_cover::Sources;
use crate::discover::is_test_source;
use crate::module::{first_part, EvidenceMap, Module};
use crate::parse::parse;
use crate::source::{declared_encoding, decode, newlines};

#[path = "outside_native.rs"]
mod native;
#[path = "outside_sites.rs"]
mod sites;

/// The package of the names of the modules of the repository outside the scan. It is no Python
/// name, so it can be the name of no module of the scan.
const OUTSIDE: &str = "<outside>";

/// The directories that the walk does not enter by their name. Each file below a test directory
/// is a test source (`is_test_source`).
const SKIPPED: [&str; 6] = [
    ".git",
    "__pycache__",
    "node_modules",
    "test",
    "tests",
    "__tests__",
];

/// The files that prove a directory as build output or as installed packages.
const MARKERS: [&str; 2] = ["CACHEDIR.TAG", "pyvenv.cfg"];

/// The files of the repository that the walk reads.
#[derive(Default)]
struct Files {
    python: Vec<String>,
    native: Vec<String>,
}

/// The modules of `scan` that code of the repository outside the scan can write.
pub(super) fn written(
    snapshot: &mut Snapshot,
    scan: &mut Vec<Module>,
    selected: &[String],
    namespace: &str,
) -> HashSet<String> {
    let names: HashSet<String> = scan.iter().map(|module| module.name.clone()).collect();
    let selected: HashSet<&str> = selected.iter().map(String::as_str).collect();
    let mut files = walk(snapshot, &selected);
    let mut outside = Vec::new();
    for rel in &files.python {
        match read(snapshot, rel, outside.len()) {
            Read::Module(module) => outside.push(*module),
            Read::Silent => {}
            Read::Opaque => files.native.push(rel.clone()),
        }
    }
    let mut found = native::named(snapshot, &files.native, &names);
    let binders: Vec<Binders> = outside
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let (literals, hazards) = super::hazards::split(&outside, &binders, None);
    for (_, _, target) in &literals {
        found.extend(native::reached(target, &names));
    }
    for (index, site) in &hazards {
        let module = &outside[*index];
        if !sites::harmless(site, module, &names) {
            found.extend(sites::named(module, &names));
        }
    }
    found.extend(escaped(scan, outside, namespace));
    found
}

/// What the read of one Python file gives.
enum Read {
    /// A module to read.
    Module(Box<Module>),
    /// A file that Python cannot run.
    Silent,
    /// A file that Python can run and the collector cannot read.
    Opaque,
}

fn read(snapshot: &mut Snapshot, rel: &str, index: usize) -> Read {
    let Some(raw) = snapshot.read(rel) else {
        // A file that is absent or that does not read is a problem of the snapshot, so a gap.
        return if snapshot.size_gap(rel).is_some() {
            Read::Opaque
        } else {
            Read::Silent
        };
    };
    if declared_encoding(&raw).is_err() {
        return Read::Opaque;
    }
    let Some(text) = decode(&raw) else {
        return Read::Silent;
    };
    let text = newlines(text).into_owned();
    match parse(&text, PyMinor::Py314) {
        Ok(tree) => {
            let name = format!("{OUTSIDE}.f{index}");
            Read::Module(Box::new(Module::new(rel.to_owned(), name, text, tree)))
        }
        Err(_) => Read::Silent,
    }
}

/// The modules of the scan that the escape rule of AD-504 finds in `outside`. Only a file that
/// spells the first part of a module of the scan can bind one by an import.
fn escaped(scan: &mut Vec<Module>, files: Vec<Module>, namespace: &str) -> HashSet<String> {
    let parts: HashSet<String> = scan
        .iter()
        .map(|module| first_part(&module.name).to_owned())
        .collect();
    let count = scan.len();
    scan.extend(files.into_iter().filter(|module| {
        parts
            .iter()
            .any(|part| module.text().contains(part.as_str()))
    }));
    if scan.len() == count {
        return HashSet::new();
    }
    let binders: Vec<Binders> = scan
        .iter()
        .map(|module| Binders::of(&module.tree))
        .collect();
    let none = HashSet::new();
    let mut sources = Sources::new();
    let mut evidence = EvidenceMap::new();
    let context = (&none, &sources);
    let records = imports::collect_all(scan, &binders, namespace, &mut evidence, context, &[]);
    // The uses of an outside file follow its names through the records of the scan, so both
    // walks read all records; the escapes that the scan alone gives are not its own.
    let all = super::uses::settled(scan, &records.records, &mut sources.clone());
    scan.truncate(count);
    let own: Vec<_> = (records.records.into_iter())
        .filter(|record| !outside(record.data.data().source_module.as_str()))
        .collect();
    let inside = super::uses::settled(scan, &own, &mut sources);
    let names: HashSet<&str> = scan.iter().map(|module| module.name.as_str()).collect();
    (all.into_iter())
        .filter(|name| names.contains(name.as_str()) && !inside.contains(name))
        .collect()
}

/// True for the name of a module of the repository outside the scan.
fn outside(name: &str) -> bool {
    name.starts_with(OUTSIDE)
}

/// The Python files and the extension files of the snapshot outside the scan modules.
fn walk(snapshot: &mut Snapshot, selected: &HashSet<&str>) -> Files {
    let mut files = Files::default();
    let mut pending = vec![String::new()];
    while let Some(directory) = pending.pop() {
        let Some(entries) = snapshot.listing(if directory.is_empty() {
            "."
        } else {
            &directory
        }) else {
            continue;
        };
        let names: HashMap<&str, Entry> = entries.iter().map(|(n, e)| (n.as_str(), *e)).collect();
        if MARKERS
            .iter()
            .any(|marker| names.get(marker) == Some(&Entry::File))
        {
            continue;
        }
        for (name, entry) in &entries {
            let rel = join(&directory, name);
            match entry {
                Entry::Directory if !SKIPPED.contains(&name.as_str()) => pending.push(rel),
                Entry::File if !selected.contains(rel.as_str()) && !is_test_source(&rel) => {
                    files.add(rel);
                }
                _ => {}
            }
        }
    }
    files.python.sort();
    files.native.sort();
    files
}

impl Files {
    fn add(&mut self, rel: String) {
        if rel.ends_with(".py") || rel.ends_with(".pyw") {
            self.python.push(rel);
        } else if native::extension(&rel) {
            self.native.push(rel);
        }
    }
}

#[cfg(test)]
#[path = "outside_tests.rs"]
mod tests;
