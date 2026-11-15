// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The decision of a candidate `sys.path.append` (AD-538): drop it when its directory adds no
//! module-like entry that the scan imports (R2, R3, R4 of `syspath.rs`), else it is the gap
//! `import_system_change` of the whole run. The listing of the directory is a reply input.

use std::collections::{BTreeSet, HashMap, HashSet};

use archkeel_facts::{ImportFact, Record};
use archkeel_snapshot::Snapshot;

use super::hazards::{Site, IMPORT_SYSTEM};
use super::syspath::PATH_WRITE;
use crate::module::Module;

/// The listing of a directory that a verdict depends on: the path and the sorted names.
pub(crate) struct Listing {
    pub path: String,
    pub text: String,
}

/// What the survey knows for the decision of every write.
pub(super) struct Scan<'s> {
    pub modules: &'s [Module],
    pub imports: &'s [Record<ImportFact>],
    pub roots: &'s [String],
    pub namespace: &'s str,
}

impl<'s> Scan<'s> {
    /// AD-538: the facts of the scan that decide whether a write to `sys.path` adds an imported name.
    pub(super) fn new(
        modules: &'s [Module],
        imports: &'s [Record<ImportFact>],
        roots: &'s [String],
        namespace: &'s str,
    ) -> Self {
        Scan {
            modules,
            imports,
            roots,
            namespace,
        }
    }
}

/// Drop each candidate write that adds no imported name; turn each other into the gap of the
/// whole run. The listing of each directory that a dropped write depends on is returned.
pub(super) fn settle(
    found: Vec<(usize, Site)>,
    scan: &Scan<'_>,
    snapshot: &mut Snapshot,
) -> (Vec<(usize, Site)>, Vec<Listing>) {
    let conflicts = conflict_set(scan);
    let (mut kept, mut listings) = (Vec::new(), BTreeSet::new());
    for (index, site) in found {
        if site.kind != PATH_WRITE {
            kept.push((index, site));
            continue;
        }
        let levels = site.detail.parse::<usize>().unwrap_or(usize::MAX);
        match harmless(&scan.modules[index].rel, levels, &conflicts, scan, snapshot) {
            Some(listing) => {
                listings.insert((listing.path, listing.text));
            }
            None => kept.push((
                index,
                Site {
                    kind: IMPORT_SYSTEM,
                    detail: "sys.path".to_owned(),
                    range: site.range,
                },
            )),
        }
    }
    let listings = listings
        .into_iter()
        .map(|(path, text)| Listing { path, text })
        .collect();
    (kept, listings)
}

/// R2: the first segment of each import target, of the namespace and of each literal call, folded.
fn conflict_set(scan: &Scan<'_>) -> HashSet<String> {
    let first = |name: &str| name.split('.').next().unwrap_or(name).to_lowercase();
    let mut names: HashSet<String> = scan
        .imports
        .iter()
        .map(|record| first(record.data.data().target_module.as_str()))
        .collect();
    names.insert(first(scan.namespace));
    names
}

/// The listing of the directory when the write adds no imported name, else `None`.
fn harmless(
    rel: &str,
    levels: usize,
    conflicts: &HashSet<String>,
    scan: &Scan<'_>,
    snapshot: &mut Snapshot,
) -> Option<Listing> {
    let parts: Vec<&str> = rel.split('/').collect();
    if levels == 0 || levels > parts.len() {
        return None;
    }
    // R5: no link on the path of the file, and the directory is inside the snapshot.
    for end in 1..=parts.len() {
        let prefix = parts[..end].join("/");
        if snapshot.real(&prefix).as_deref() != Some(prefix.as_str()) {
            return None;
        }
    }
    let directory = parts[..parts.len() - levels].join("/");
    let place = if directory.is_empty() {
        "."
    } else {
        directory.as_str()
    };
    let (files, directories) = listed(snapshot, place)?;
    let mut count: HashMap<String, usize> = HashMap::new();
    for name in &directories {
        *count.entry(name.to_lowercase()).or_default() += 1;
    }
    for name in &files {
        if let Some(module) = module_name(name) {
            *count.entry(module).or_default() += 1;
        }
    }
    for (name, entries) in &count {
        if !conflicts.contains(name) {
            continue;
        }
        if !(entries == &1 && exempt(name, &directories, &directory, scan, snapshot)) {
            return None;
        }
    }
    let mut names: Vec<&String> = files.iter().chain(&directories).collect();
    names.sort();
    let text = names
        .iter()
        .map(|name| name.as_str())
        .collect::<Vec<_>>()
        .join("\n");
    Some(Listing {
        path: format!("{place}/"),
        text,
    })
}

/// R3: the one entry of the namespace is no new module when it is the scan root itself.
fn exempt(
    name: &str,
    directories: &[String],
    directory: &str,
    scan: &Scan<'_>,
    snapshot: &mut Snapshot,
) -> bool {
    let namespace = scan.namespace;
    if name != namespace.to_lowercase() || namespace.contains('.') {
        return false;
    }
    let place = if directory.is_empty() {
        namespace.to_owned()
    } else {
        format!("{directory}/{namespace}")
    };
    let root = scan
        .roots
        .iter()
        .any(|root| root.trim_start_matches("./") == place);
    root && directories.iter().any(|entry| entry == namespace)
        && snapshot.real(&place).as_deref() == Some(place.as_str())
        && snapshot.is_file(&format!("{place}/__init__.py"))
}

/// The files and directories of `place`, or `None` for a listing with a problem or a hidden entry.
fn listed(snapshot: &mut Snapshot, place: &str) -> Option<(Vec<String>, Vec<String>)> {
    let before = std::mem::take(&mut snapshot.problems);
    let listing = snapshot.entries(place);
    let hidden = snapshot.hidden_entries(place);
    let clean = snapshot.problems.is_empty() && hidden.is_empty();
    snapshot.problems.extend(before);
    clean.then_some(listing)
}

/// R4: the module that a file can be, without case: `n.py`, `n.pyc`, `n.pyw`, `n.so`, `n.pyd`,
/// `n.<tag>.so` and `n.<tag>.pyd`.
fn module_name(file: &str) -> Option<String> {
    let lower = file.to_lowercase();
    let suffixes = [".py", ".pyc", ".pyw", ".so", ".pyd"];
    suffixes
        .iter()
        .any(|suffix| lower.ends_with(suffix))
        .then(|| lower.split('.').next().unwrap_or(&lower).to_owned())
        .filter(|name| !name.is_empty())
}
