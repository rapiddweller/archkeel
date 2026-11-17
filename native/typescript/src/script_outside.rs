// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The repository guard of the premise (AD-540 amendment, #1546): a file of the repository outside
//! the scan roots that replaces a global withholds the native proof of that global.
//!
//! The premise says that code outside the scan roots hands in no global or platform object and
//! replaces no global. Code outside the repository is covered by the premise only. A JavaScript,
//! TypeScript or HTML file of the repository outside the scan roots is read here (test files,
//! declarations, installed packages and hidden directories excepted), and each write that
//! replaces a global is a counterexample: `window.x = …` (also `globalThis`, `self`, `frames`,
//! `top`, `parent`, `global`, `opener`), an assignment to a name that the file does not declare,
//! a top-level binding of a classic script, and the reflective writes of AD-766 on a window name.
//! A write whose name the guard cannot read withholds every global.

use std::collections::BTreeMap;

use archkeel_snapshot::paths::{join, within};
use archkeel_snapshot::Snapshot;
use tree_sitter::Node;

use crate::script_outside_forms::{writes_of, Found};
use crate::source::Span;
use crate::source_input::classify_file;
use crate::syntax::Parsers;
use crate::test_sources::is_test_source;

/// The directories that hold installed packages: their code is outside the model.
const INSTALLED: [&str; 3] = ["node_modules", "jspm_packages", "bower_components"];

/// The most files that the guard reads; a larger repository withholds every global.
const MAX_FILES: usize = 4000;

/// A write of a file outside the scan roots: the file and the place.
pub(crate) type Site = (String, Span);

/// The globals that files of the repository outside the scan roots replace.
#[derive(Default)]
pub(crate) struct Outside {
    /// The first write of each named global.
    pub names: BTreeMap<String, Site>,
    /// The first write whose name the guard cannot read, or a file that it cannot read.
    pub any: Option<Site>,
}

impl Outside {
    /// The write that withholds the proof of `name`, if any.
    pub(crate) fn withholds(&self, name: &str) -> Option<&Site> {
        BTreeMap::get(&self.names, name).or(Option::as_ref(&self.any))
    }

    /// A write names `name` (and not only a write whose name the guard cannot read).
    pub(crate) fn named(&self, name: &str) -> bool {
        BTreeMap::contains_key(&self.names, name)
    }

    fn add(&mut self, rel: &str, found: Found) {
        let site = (rel.to_owned(), found.span);
        match found.name {
            Some(name) => {
                self.names.entry(name).or_insert(site);
            }
            None => {
                self.any.get_or_insert(site);
            }
        }
    }
}

/// Read each file of the repository outside `roots` for a write that replaces a global.
pub(crate) fn read(snapshot: &mut Snapshot, parsers: &mut Parsers, roots: &[String]) -> Outside {
    let mut found = Outside::default();
    let files = outside_files(snapshot, roots);
    if Vec::len(&files) > MAX_FILES {
        found.any = Some((".".to_owned(), whole_file()));
        return found;
    }
    for rel in files {
        let Some(data) = snapshot.read(&rel) else {
            // A file that the guard cannot read can replace any global.
            found.any.get_or_insert((rel, whole_file()));
            continue;
        };
        for (typescript, module, program) in programs(&rel, &data) {
            let Some((tree, _)) = parsers.parse(typescript, &program) else {
                found.any.get_or_insert((rel.clone(), whole_file()));
                continue;
            };
            let root: Node = tree.root_node();
            for write in writes_of(root, &program, module) {
                found.add(&rel, write);
            }
        }
    }
    found
}

/// The place of a whole file.
fn whole_file() -> Span {
    Span {
        line: 1,
        end_line: 1,
        column: 0,
        excerpt: String::new(),
    }
}

/// The source files of the repository outside the scan roots, sorted.
fn outside_files(snapshot: &mut Snapshot, roots: &[String]) -> Vec<String> {
    let inside = |path: &str| roots.iter().any(|root| within(root, path));
    let mut found = Vec::new();
    let mut pending = vec![".".to_owned()];
    while let Some(directory) = pending.pop() {
        let (files, children) = snapshot.entries(&directory);
        for name in files {
            let rel = join(&directory, &name);
            if !inside(&rel) && outside_source(&rel) {
                Vec::push(&mut found, rel);
            }
        }
        for child in children {
            let path = join(&directory, &child);
            let skipped = child.starts_with('.') || INSTALLED.contains(&String::as_str(&child));
            // A directory below a scan root is scanned; a directory above one is walked for its
            // other entries.
            if !skipped && !inside(&path) {
                Vec::push(&mut pending, path);
            }
        }
        if Vec::len(&found) > MAX_FILES {
            break;
        }
    }
    found.sort();
    found
}

/// A JavaScript, TypeScript or HTML file that is no declaration and no test file.
fn outside_source(rel: &str) -> bool {
    if is_test_source(rel) {
        return false;
    }
    let lower = rel.to_ascii_lowercase();
    let page = lower.ends_with(".html") || lower.ends_with(".htm");
    let code = classify_file(rel).is_some_and(|suffix| {
        matches!(
            suffix.source_kind(),
            Some(
                crate::source_input::SourceKind::JavaScript
                    | crate::source_input::SourceKind::TypeScript
            )
        )
    });
    page || code
}

/// The programs of a file: the grammar (TypeScript or TSX), whether the program is a module by
/// its element (`type="module"`), and the bytes. A code file is one program; a page gives one
/// program for each inline script, each with the other bytes blanked so that the lines stay the
/// lines of the page.
fn programs(rel: &str, data: &[u8]) -> Vec<(bool, bool, Vec<u8>)> {
    match classify_file(rel) {
        Some(suffix) => vec![(suffix.parser_typescript(), false, data.to_vec())],
        None => crate::script_outside_forms::inline_scripts(data)
            .into_iter()
            .map(|(module, program)| (false, module, program))
            .collect(),
    }
}

#[cfg(test)]
#[path = "script_outside_tests.rs"]
mod tests;
