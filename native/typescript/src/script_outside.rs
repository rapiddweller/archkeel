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
use crate::source_input::{classify_file, installed_directory, skipped_directory};
use crate::syntax::Parsers;
use crate::test_sources::is_test_source;

/// The directories that hold installed third-party packages. Their code is code outside the scan
/// roots, so the premise covers it; the guard reads the code of the repository itself.
/// A write of a file outside the scan roots: the file and the place.
pub(crate) type Site = (String, Span);

/// The globals that files of the repository outside the scan roots replace.
#[derive(Default)]
pub(crate) struct Outside {
    /// The first write of each named global.
    pub names: BTreeMap<String, Site>,
    /// The first write whose name the guard cannot read, or a file that it cannot parse.
    pub any: Option<Site>,
    /// Why the guard did not read every candidate file: then no global has a native proof.
    pub incomplete: Option<String>,
    /// The member patches of each global (#1674): the written path (see `Found::patch`) and the
    /// write.
    pub patches: BTreeMap<String, Vec<(Vec<String>, Site)>>,
    /// The stated generated copies of scanned sources that the guard does not read.
    pub generated: Vec<String>,
    /// The first code address of a data file below a scan root (#1662, AD-810).
    pub address: Option<Site>,
}

impl Outside {
    /// The write that withholds the proof of `name`, if any.
    pub(crate) fn withholds(&self, name: &str) -> Option<&Site> {
        BTreeMap::get(&self.names, name)
            .or(Option::as_ref(&self.any))
            .or(Option::as_ref(&self.address))
    }

    /// The site is the code address of a data file, not a write of a file outside the roots.
    pub(crate) fn is_address(&self, site: (&str, &Span)) -> bool {
        Option::as_ref(&self.address).is_some_and(|(rel, span)| (String::as_str(rel), span) == site)
    }

    /// A write names `name` (and not only a write whose name the guard cannot read).
    pub(crate) fn named(&self, name: &str) -> bool {
        BTreeMap::contains_key(&self.names, name)
    }

    fn add(&mut self, rel: &str, found: Found) {
        let site = (rel.to_owned(), found.span);
        if let (Some(member), Some(global)) = (found.patch, found.name.clone()) {
            Vec::push(
                BTreeMap::entry(&mut self.patches, global).or_default(),
                (member, site),
            );
            return;
        }
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

/// Read repository files outside `roots` and repository-named preload closures for global writes.
pub(crate) fn read(
    snapshot: &mut Snapshot,
    parsers: &mut Parsers,
    roots: &[String],
    preloads: &[String],
) -> Outside {
    let mut found = Outside::default();
    let mut files = outside_files(snapshot, roots);
    Vec::extend(&mut files, preloads.iter().cloned());
    let count = Vec::len(&files);
    // The code address of a data file below a scan root (#1662, AD-810).
    found.address = addresses(snapshot, roots);
    for rel in files {
        let Some(data) = snapshot.read(&rel) else {
            // A file that the guard cannot read can replace any global. It is no digested input,
            // so the cause names it and no evidence cites it.
            found.incomplete.get_or_insert_with(|| unread(&rel, count));
            continue;
        };
        // A stated generated copy of scanned sources is the code of its sources (AD-788).
        if crate::script_outside_generated::stated_copy(snapshot, &rel, &data, roots) {
            Vec::push(&mut found.generated, rel);
            continue;
        }
        let page = classify_file(&rel).is_none();
        let preload = preloads.contains(&rel);
        for (typescript, module, program) in programs(&rel, &data) {
            // Node loads preloads as modules, not classic scripts.
            let module = module || preload;
            let named = if page {
                format!("{rel}.js")
            } else if preload {
                format!("{rel}.cjs")
            } else {
                rel.clone()
            };
            for write in crate::script_outside_detector::detected(parsers, &named, &program) {
                found.add(&rel, write);
            }
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

/// The first JSON or YAML file below a scan root whose text holds a code address, with its line.
/// A file that the guard cannot read counts as such a file.
fn addresses(snapshot: &mut Snapshot, roots: &[String]) -> Option<Site> {
    for rel in data_files(snapshot, roots) {
        let Some(data) = snapshot.read(&rel) else {
            return Some((rel, at_line(1)));
        };
        let text = String::from_utf8_lossy(&data);
        if !crate::source_input::code_address(&text) {
            continue;
        }
        let line = text
            .lines()
            .position(crate::source_input::code_address)
            .map_or(1, |index| index + 1);
        return Some((rel, at_line(line)));
    }
    None
}

/// The JSON and YAML files below the scan roots, without installed and hidden directories, sorted.
fn data_files(snapshot: &mut Snapshot, roots: &[String]) -> Vec<String> {
    let mut found = Vec::new();
    let mut pending: Vec<String> = roots.to_vec();
    while let Some(directory) = Vec::pop(&mut pending) {
        if snapshot.is_file(&directory) {
            if data_file(&directory) {
                Vec::push(&mut found, directory);
            }
            continue;
        }
        let (files, children) = snapshot.entries(&directory);
        let data = files
            .iter()
            .map(|name| join(&directory, name))
            .filter(|rel| data_file(rel) && roots.iter().any(|root| within(root, rel)));
        Vec::extend(&mut found, data);
        let walked = children
            .iter()
            .filter(|name| !name.starts_with('.') && !installed_directory(name))
            .map(|name| join(&directory, name));
        Vec::extend(&mut pending, walked);
    }
    found.sort();
    found.dedup();
    found
}

/// A file with a JSON or YAML suffix, in any letter case.
fn data_file(rel: &str) -> bool {
    let lower = str::to_ascii_lowercase(rel);
    [".json", ".yaml", ".yml"]
        .iter()
        .any(|suffix| lower.ends_with(suffix))
}

/// The place of one line of a file.
fn at_line(line: usize) -> Span {
    let line = i64::try_from(line).unwrap_or(i64::MAX);
    Span {
        line,
        end_line: line,
        column: 0,
        excerpt: String::new(),
    }
}

/// The cause of a run whose guard cannot read a file: the file, the count, and what to do.
fn unread(rel: &str, count: usize) -> String {
    format!(
        "the global-writer guard cannot read {rel}, one of the {count} files outside the scan \
         roots (over the size limit of a file or the input limit of a scan); move --root to the \
         part of the repository that runs, or make the file smaller"
    )
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
            let name = String::as_str(&child);
            let skipped = skipped_directory(name);
            // A directory below a scan root is scanned; a directory above one is walked for its
            // other entries.
            if !skipped && !inside(&path) {
                Vec::push(&mut pending, path);
            }
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
        None => crate::script_outside_page::inline_scripts(data)
            .into_iter()
            .map(|(module, program)| (false, module, program))
            .collect(),
    }
}

#[cfg(test)]
#[path = "script_outside_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "script_member_patch_tests.rs"]
mod member_patch_tests;
