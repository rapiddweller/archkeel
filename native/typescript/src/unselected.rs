// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The project source under the scan roots, found without the TSConfig (AD-488).
//!
//! The TSConfig selects the files that the collector reads (`files`, `include`, `exclude`,
//! `allowJs`). A file that the TSConfig drops can hold an import, so a file of this list that the
//! collection does not read is a coverage gap. A name or a directory does not prove that a file
//! is generated, so emitted names and build output directories are project source too.
//!
//! One directory is not project source: an installed-package directory (`node_modules`,
//! `jspm_packages` beside a `package.json`, `bower_components` beside a `bower.json`) that the
//! package manager owns. The project reaches its code only as an external package, which the
//! external rules read. The directory is project source again when the TSConfig selects a file in
//! it, or when an import that the collector read resolves to a local file in it.

use std::collections::BTreeSet;

use crate::source_input::{classify_file, SourceKind, Suffix};
use archkeel_snapshot::paths::{join, within};
use archkeel_snapshot::Snapshot;

/// An installed-package directory name and the manifest of the package manager beside it.
const INSTALLED: [(&str, &str); 3] = [
    ("node_modules", "package.json"),
    ("jspm_packages", "package.json"),
    ("bower_components", "bower.json"),
];

/// Each project source file under `roots`, sorted. `used` are the files that the TSConfig selects
/// or that a read import resolves to: an installed-package directory that holds one is walked.
pub(crate) fn project_sources(
    snapshot: &mut Snapshot,
    roots: &[String],
    used: &BTreeSet<String>,
) -> Vec<String> {
    let mut found = BTreeSet::new();
    let mut seen = BTreeSet::new();
    for root in roots {
        if snapshot.is_file(root) {
            if source(root) {
                found.insert(root.clone());
            }
            continue;
        }
        let mut pending = vec![root.clone()];
        while let Some(directory) = pending.pop() {
            // An exempt directory is skipped before this point, so it marks no real path as seen.
            if snapshot
                .real(&directory)
                .is_some_and(|real| seen.insert(real))
            {
                pending.extend(visit(snapshot, &directory, used, &mut found));
            }
        }
    }
    found.into_iter().collect()
}

/// Add the source files of `directory` to `found`; give the child directories to walk.
fn visit(
    snapshot: &mut Snapshot,
    directory: &str,
    used: &BTreeSet<String>,
    found: &mut BTreeSet<String>,
) -> Vec<String> {
    let (files, children) = snapshot.entries(directory);
    for name in files.iter().filter(|name| source(name)) {
        found.insert(join(directory, name));
    }
    let manifests: BTreeSet<&str> = files.iter().map(String::as_str).collect();
    children
        .into_iter()
        .filter(|child| {
            let path = join(directory, child);
            !INSTALLED.iter().any(|(name, manifest)| {
                child == name
                    && manifests.contains(manifest)
                    && !used.iter().any(|file| within(&path, file))
            })
        })
        .map(|child| join(directory, &child))
        .collect()
}

/// True for a TypeScript, declaration or JavaScript file name, in any letter case.
fn source(name: &str) -> bool {
    classify_file(&name.to_ascii_lowercase())
        .and_then(Suffix::source_kind)
        .is_some_and(|kind| !matches!(kind, SourceKind::Json))
}

#[cfg(test)]
#[path = "unselected_tests.rs"]
mod tests;
