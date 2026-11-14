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
//! The code of an installed package is outside the model. A package in an installed-package
//! directory (`node_modules` or `jspm_packages` beside a `package.json`, `bower_components` beside
//! a `bower.json`, each manifest a JSON object) is not listed while nothing reaches it except a
//! `node_modules` search. It is listed when a path of `reach` lies in it or holds it: a file that
//! the TSConfig selects, a file that an import resolves to by an alias, `baseUrl`, `rootDirs` or a
//! relative path, a `typeRoots` entry, or a candidate of a `types` name or a `reference types`
//! directive. A bare import that a `node_modules` search resolves stays outside: an open limit.

use std::collections::BTreeSet;

use serde_json::{Map, Value};

use crate::source_input::{classify_file, SourceKind, Suffix};
use archkeel_snapshot::paths::{dirname, join, within};
use archkeel_snapshot::Snapshot;

/// An installed-package directory name and the manifest of the package manager beside it.
const INSTALLED: [(&str, &str); 3] = [
    ("node_modules", "package.json"),
    ("jspm_packages", "package.json"),
    ("bower_components", "bower.json"),
];

/// Each project source file under `roots`, sorted, and each package that `reach` makes source.
pub(crate) fn project_sources(
    snapshot: &mut Snapshot,
    roots: &[String],
    reach: &BTreeSet<String>,
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
            // An exempt package is skipped before this point, so it marks no real path as seen.
            if snapshot
                .real(&directory)
                .is_some_and(|real| seen.insert(real))
            {
                pending.extend(visit(snapshot, &directory, reach, &mut found));
            }
        }
    }
    found.into_iter().collect()
}

/// Add the source files of `directory` to `found`; give the directories to walk.
fn visit(
    snapshot: &mut Snapshot,
    directory: &str,
    reach: &BTreeSet<String>,
    found: &mut BTreeSet<String>,
) -> Vec<String> {
    let (files, children) = snapshot.entries(directory);
    for name in files.iter().filter(|name| source(name)) {
        found.insert(join(directory, name));
    }
    let mut walk = Vec::new();
    for child in children {
        let path = join(directory, &child);
        let manifest = INSTALLED.iter().find(|(name, _)| child == *name);
        match manifest.filter(|(_, file)| files.iter().any(|f| f == file)) {
            Some((_, file)) if object(snapshot, &join(directory, file)) => {
                walk.extend(reached(snapshot, &path, reach, found));
            }
            _ => walk.push(path),
        }
    }
    walk
}

/// The packages of an installed directory that a path of `reach` lies in or holds. A file that
/// lies in the directory itself or in a scope directory is listed when a path of `reach` lies in
/// that directory.
fn reached(
    snapshot: &mut Snapshot,
    installed: &str,
    reach: &BTreeSet<String>,
    found: &mut BTreeSet<String>,
) -> Vec<String> {
    let touches = |path: &str| reach.iter().any(|r| within(path, r) || within(r, path));
    let mut walk = Vec::new();
    let mut directories = vec![installed.to_owned()];
    while let Some(directory) = directories.pop() {
        let (files, children) = snapshot.entries(&directory);
        if reach.iter().any(|r| within(&directory, r)) {
            let sources = files.iter().filter(|name| source(name));
            found.extend(sources.map(|name| join(&directory, name)));
        }
        for child in children {
            let path = join(&directory, &child);
            if child.starts_with('@') && directory == installed {
                directories.push(path);
            } else if touches(&path) {
                walk.push(path);
            }
        }
    }
    walk
}

/// True when the manifest is a file that holds a JSON object.
fn object(snapshot: &mut Snapshot, manifest: &str) -> bool {
    snapshot
        .read(manifest)
        .is_some_and(|bytes| serde_json::from_slice::<Map<String, Value>>(&bytes).is_ok())
}

/// True for a TypeScript, declaration or JavaScript file name, in any letter case.
fn source(name: &str) -> bool {
    classify_file(&name.to_ascii_lowercase())
        .and_then(Suffix::source_kind)
        .is_some_and(|kind| !matches!(kind, SourceKind::Json))
}

/// The paths where the compiler looks for the type package `name` from `directory`: each
/// `node_modules/@types/<name>` and `node_modules/<name>` up to the snapshot root.
pub(crate) fn type_candidates(directory: &str, name: &str) -> Vec<String> {
    let mangled = name
        .strip_prefix('@')
        .map_or_else(|| name.to_owned(), |scoped| scoped.replacen('/', "__", 1));
    let mut candidates = Vec::new();
    let mut current = directory.to_owned();
    loop {
        candidates.push(join(&current, &format!("node_modules/@types/{mangled}")));
        candidates.push(join(&current, &format!("node_modules/{name}")));
        if current == "." || current.is_empty() {
            return candidates;
        }
        current = match dirname(&current) {
            "" => ".".to_owned(),
            parent => parent.to_owned(),
        };
    }
}

/// What the type options of a TSConfig in `own` reach: each `typeRoots` entry, and each `types`
/// name in each root, or in each `node_modules/@types` up to the snapshot root.
pub(crate) fn type_reach(own: &str, compiler: &Map<String, Value>) -> Vec<String> {
    let texts = |key: &str| -> Vec<String> {
        let list = compiler.get(key).and_then(Value::as_array);
        let items = list.into_iter().flatten().filter_map(Value::as_str);
        items.map(str::to_owned).collect()
    };
    let roots: Vec<String> = texts("typeRoots")
        .iter()
        .map(|root| join(own, root.trim_start_matches("${configDir}/")))
        .collect();
    let mut reach = roots.clone();
    for name in texts("types") {
        reach.extend(roots.iter().map(|root| join(root, &name)));
        reach.extend(type_candidates(own, &name));
    }
    reach
}

/// The names of the leading `/// <reference types="..." />` directives of a source text.
pub(crate) fn reference_types(text: &str) -> Vec<String> {
    let mut names = Vec::new();
    for line in text.lines().map(str::trim) {
        if line.is_empty() || (line.starts_with("//") && !line.starts_with("///")) {
            continue;
        }
        let Some(rest) = line.strip_prefix("///") else {
            break;
        };
        let rest = rest.trim_start();
        if !rest.to_ascii_lowercase().starts_with("<reference") {
            continue;
        }
        for quote in ['"', '\''] {
            let marker = format!("types={quote}");
            if let Some((_, tail)) = rest.split_once(&marker) {
                names.extend(tail.split(quote).next().map(str::to_owned));
            }
        }
    }
    names
}

#[cfg(test)]
#[path = "unselected_tests.rs"]
mod tests;
