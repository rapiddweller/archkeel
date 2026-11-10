// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What is specific to Rust in the read of a snapshot. `archkeel-snapshot` owns the reads, the
//! containment, the symlink rule and the size limit; this file only names a failed read and
//! lists the source files below a directory.

use std::collections::BTreeSet;

use archkeel_snapshot::Snapshot;

/// The deepest directory that the walk enters.
const MAX_DEPTH: usize = 128;

/// Read a file as text. The reason of a failure names the file. A path that leaves the snapshot
/// is never read: `archkeel-snapshot` refuses it and records a problem, which is a gap.
pub fn read_text(snapshot: &mut Snapshot, rel: &str) -> Result<String, String> {
    match snapshot.read(rel) {
        Some(bytes) => Ok(String::from_utf8_lossy(&bytes).into_owned()),
        None => Err(snapshot.size_gap(rel).unwrap_or_else(|| {
            format!("Unreadable file, or a path that leaves the snapshot: {rel}")
        })),
    }
}

/// The files below `rel`, relative to the snapshot, sorted. A directory named `target` and a
/// hidden directory are not entered. A directory is entered once, so a link cannot make a loop.
pub fn walk(snapshot: &mut Snapshot, rel: &str) -> Vec<String> {
    let mut found = Vec::new();
    let mut seen = BTreeSet::new();
    walk_into(snapshot, rel, 0, &mut seen, &mut found);
    found.sort();
    found
}

fn walk_into(
    snapshot: &mut Snapshot,
    rel: &str,
    depth: usize,
    seen: &mut BTreeSet<String>,
    found: &mut Vec<String>,
) {
    if depth > MAX_DEPTH || !seen.insert(snapshot.real(rel).unwrap_or_else(|| rel.to_owned())) {
        return;
    }
    let (files, directories) = snapshot.entries(rel);
    let child = |name: &str| archkeel_snapshot::paths::join(rel, name);
    found.extend(files.iter().map(|name| child(name)));
    for name in directories {
        if name != "target" && !name.starts_with('.') {
            walk_into(snapshot, &child(&name), depth + 1, seen, found);
        }
    }
}

#[cfg(test)]
#[path = "source_tests.rs"]
mod tests;
