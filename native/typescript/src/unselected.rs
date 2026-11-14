// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The project source under the scan roots, found without the TSConfig (AD-488).
//!
//! The TSConfig selects the files that the collector reads (`files`, `include`, `exclude`,
//! `allowJs`). A file that the TSConfig drops can hold an import, so a file of this list that the
//! collection does not read is a coverage gap. The list leaves out what is not project source:
//! - a file under `node_modules`, `bower_components` or `jspm_packages`;
//! - a file under the `outDir` or `declarationDir` of the TSConfig;
//! - a file that a source of the same stem shadows, as `a.js` or `a.d.ts` beside `a.ts`: the
//!   compiler writes these files next to their source when no `outDir` is set;
//! - a file whose suffix is not TypeScript, a declaration or JavaScript.

use std::collections::BTreeSet;

use crate::source_input::{classify_file, shadowed, Suffix};
use archkeel_snapshot::paths::{join, within};
use archkeel_snapshot::Snapshot;

/// The directory names that hold installed packages, never project source.
const INSTALLED: [&str; 3] = ["node_modules", "bower_components", "jspm_packages"];

/// Each project source file under `roots`, sorted. `outputs` are the build output directories.
pub(crate) fn project_sources(
    snapshot: &mut Snapshot,
    roots: &[String],
    outputs: &[String],
) -> Vec<String> {
    // An output directory that holds a scan root does not hide that root: the roots name the source.
    let outputs: Vec<&String> = outputs
        .iter()
        .filter(|out| !roots.iter().any(|root| within(out, root)))
        .collect();
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
            let fresh = snapshot
                .real(&directory)
                .is_some_and(|real| seen.insert(real));
            if fresh && !outputs.iter().any(|out| within(out, &directory)) {
                pending.extend(visit(snapshot, &directory, &mut found));
            }
        }
    }
    found.into_iter().collect()
}

/// Add the source files of `directory` to `found`; give the child directories to walk.
fn visit(snapshot: &mut Snapshot, directory: &str, found: &mut BTreeSet<String>) -> Vec<String> {
    let (files, children) = snapshot.entries(directory);
    let names: BTreeSet<&str> = files.iter().map(String::as_str).collect();
    let emitted = |name: &str| shadowed(name, &|other| names.contains(other));
    for name in files.iter().filter(|name| source(name) && !emitted(name)) {
        found.insert(join(directory, name));
    }
    children
        .into_iter()
        .filter(|child| !INSTALLED.contains(&child.as_str()))
        .map(|child| join(directory, &child))
        .collect()
}

/// True for a TypeScript, declaration or JavaScript file name.
fn source(name: &str) -> bool {
    classify_file(name)
        .and_then(Suffix::source_kind)
        .is_some_and(|kind| !matches!(kind, crate::source_input::SourceKind::Json))
}

#[cfg(test)]
#[path = "unselected_tests.rs"]
mod tests;
