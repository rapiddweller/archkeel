// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module tree of each crate: from the file of a target, through each `mod name;`.
//!
//! `syn` parses a file, not a crate, so the walk follows the `mod` declarations itself. A file
//! that is in no tree is not guessed to belong to a crate: the caller reports it as UNKNOWN.

use std::collections::{BTreeSet, VecDeque};

use crate::crates::{Crate, Problem, Root, Workspace};
use crate::nesting::{too_deep, MAX_NESTING};
use crate::paths::normalize;
use crate::scan::{scan, Child, Scan};
use crate::source::read_text;
use crate::test_scope::in_test_directory;
use alternatives::release;
use archkeel_snapshot::paths::{dirname, join};
use archkeel_snapshot::Snapshot;

/// The `cfg` alternatives of one module name.
#[path = "alternatives.rs"]
mod alternatives;

/// One file of a module tree, read and scanned.
pub struct Module {
    pub rel: String,
    pub module: String,
    pub crate_index: usize,
    /// The first line of the file, trimmed at its end: the evidence of the file. The walk does
    /// not keep the text, which only this line and `blank` need.
    pub first_line: String,
    pub blank: bool,
    pub scan: Scan,
}

pub struct Walked {
    pub modules: Vec<Module>,
    pub problems: Vec<Problem>,
    /// The files that no module tree reaches are those of `files` that are not here.
    pub claimed: BTreeSet<String>,
    /// The test scope of a request that excludes tests: the files that the walk read for their
    /// `mod x;` declarations and then left out. They are claimed, but they are no modules.
    pub tests: BTreeSet<String>,
    /// The module ids that the walk gave out.
    names: BTreeSet<String>,
    exclude_tests: bool,
}

impl Walked {
    /// Whether the request leaves this file out as test scope.
    pub fn is_excluded(&self, rel: &str) -> bool {
        self.exclude_tests && (self.tests.contains(rel) || in_test_directory(rel))
    }
}

/// A file that waits for its scan.
struct Pending {
    rel: String,
    module: String,
    /// The directory where the `mod` declarations of this file look for their files.
    owner: String,
    /// How many modules lie between this file and the root of its target.
    depth: usize,
    /// The file is test scope and the request excludes tests.
    test: bool,
}

/// The deepest module that the walk reads. A name holds the whole path, so the reply grows with
/// the square of the depth; the deepest module of the `uv` corpus has depth 4.
pub const MAX_MODULE_DEPTH: usize = 64;

pub fn walk(source: &mut Snapshot, workspace: &Workspace, exclude_tests: bool) -> Walked {
    let mut walked = Walked {
        modules: Vec::new(),
        problems: Vec::new(),
        claimed: BTreeSet::new(),
        tests: BTreeSet::new(),
        names: BTreeSet::new(),
        exclude_tests,
    };
    // A crate walks the files of its own directory first. A file that another crate names, such
    // as a shared build script, then belongs to the crate that holds it and is walked once.
    for inside in [true, false] {
        for (index, krate) in workspace.crates.iter().enumerate() {
            for root in krate
                .roots
                .iter()
                .filter(|root| krate.holds(root) == inside)
            {
                walked.start(source, index, krate, root);
            }
        }
    }
    walked
}

impl Walked {
    fn start(&mut self, source: &mut Snapshot, index: usize, krate: &Crate, root: &Root) {
        if !self.claimed.insert(root.rel.clone()) {
            let reason = format!("The file {} is the file of two crates", root.rel);
            self.both(&reason, &root.rel, &join(&krate.dir, "Cargo.toml"));
            return;
        }
        self.names.insert(root.module.clone());
        if self.exclude_tests && !root.test && in_test_directory(&root.rel) {
            self.hidden(&root.rel, &root.rel);
        }
        let first = Pending {
            rel: root.rel.clone(),
            module: root.module.clone(),
            owner: dirname(&root.rel).to_owned(),
            depth: 0,
            test: self.exclude_tests && (root.test || in_test_directory(&root.rel)),
        };
        self.crate_tree(source, index, krate, first);
    }

    /// A module id that no other file has. Rust refuses two modules of one name in one parent,
    /// unless `cfg` leaves one of them out: so a second file for the same id is a cfg alternative
    /// and keeps its own file and edges under a suffixed id. A path to the id names the first.
    fn distinct(&mut self, module: String) -> String {
        let mut chosen = module.clone();
        let mut number = 2;
        while !self.names.insert(chosen.clone()) {
            chosen = format!("{module}_alt{number}");
            number += 1;
        }
        chosen
    }

    /// A gap on the file that two owners load and on the file of the second owner, so that the
    /// first owner is UNKNOWN as well as the second.
    fn both(&mut self, reason: &str, shared: &str, second: &str) {
        for file in [shared, second] {
            self.problems.push(Problem {
                reason: reason.to_owned(),
                file: file.to_owned(),
            });
        }
    }

    fn crate_tree(&mut self, source: &mut Snapshot, index: usize, krate: &Crate, first: Pending) {
        let mut queue = VecDeque::from([first]);
        while let Some(file) = queue.pop_front() {
            let Some(text) = self.read(source, &file) else {
                continue;
            };
            let scanned = self.scanned(&file, &text, krate);
            for child in &scanned.children {
                self.child(source, krate, &file, child, &mut queue);
            }
            if file.test {
                self.tests.insert(file.rel);
                continue;
            }
            let first = text.split('\n').next().unwrap_or("");
            self.modules.push(Module {
                rel: file.rel,
                module: file.module,
                crate_index: index,
                first_line: first.trim_end().to_owned(),
                blank: text.trim().is_empty(),
                scan: scanned,
            });
        }
    }

    /// Whether the file of a child is test scope under this request. A production module in a test
    /// directory is test scope too, and a gap.
    fn test_scope(&mut self, parent: &Pending, child: &Child, rel: &str) -> bool {
        let scoped = parent.test || child.test;
        let directory = in_test_directory(rel);
        if self.exclude_tests && directory && !scoped {
            self.hidden(rel, &parent.rel);
        }
        self.exclude_tests && (scoped || directory)
    }

    /// A production file in a test directory leaves the reply, because the host refuses a reply that
    /// selects a test source by its path. That must not be silent: its facts are missing.
    fn hidden(&mut self, rel: &str, file: &str) {
        let reason = format!(
            "Production source is in a test directory and the request excludes tests: {rel}"
        );
        self.problems.push(Problem {
            reason,
            file: file.to_owned(),
        });
    }

    /// The text of a file. A test file that cannot be read is out of scope, so it is no problem.
    fn read(&mut self, source: &mut Snapshot, file: &Pending) -> Option<String> {
        match read_text(source, &file.rel) {
            Ok(text) => {
                if !file.test {
                    source.select(&file.rel);
                }
                Some(text)
            }
            Err(reason) => {
                if !file.test {
                    let file = file.rel.clone();
                    self.problems.push(Problem { reason, file });
                }
                None
            }
        }
    }

    /// The scan of one file. A file that is too deep or has a syntax error gives no facts.
    fn scanned(&mut self, file: &Pending, text: &str, krate: &Crate) -> Scan {
        let failure = if too_deep(text) {
            Some(format!(
                "Brackets nest deeper than {MAX_NESTING} in {}",
                file.rel
            ))
        } else {
            let production = self.exclude_tests && !file.test;
            match scan(text, &krate.manifest.features, production) {
                Ok(mut scanned) => {
                    release(&mut scanned);
                    return scanned;
                }
                Err(error) => Some(format!("Syntax error in {}: {error}", file.rel)),
            }
        };
        if let Some(reason) = failure.filter(|_| !file.test) {
            self.problems.push(Problem {
                reason,
                file: file.rel.clone(),
            });
        }
        Scan::default()
    }

    fn child(
        &mut self,
        source: &mut Snapshot,
        krate: &Crate,
        parent: &Pending,
        child: &Child,
        queue: &mut VecDeque<Pending>,
    ) {
        let name = child.name.trim_start_matches("r#");
        let found = locate(source, parent, child, name);
        let (rel, path_loaded) = match found {
            Ok(found) => found,
            Err(reason) => {
                let out_of_scope = self.exclude_tests && (parent.test || child.test);
                if !out_of_scope {
                    let file = parent.rel.clone();
                    self.problems.push(Problem { reason, file });
                }
                return;
            }
        };
        if path_loaded && !krate.contains(&rel) {
            let reason = format!("A path attribute leaves the crate directory: {rel}");
            self.both(&reason, &rel, &parent.rel);
            return;
        }
        let test = self.test_scope(parent, child, &rel);
        if !self.claimed.insert(rel.clone()) {
            let reason = format!("The file {rel} is the file of two modules");
            self.both(&reason, &rel, &parent.rel);
            return;
        }
        let depth = parent.depth + 1 + child.inline.len();
        if depth > MAX_MODULE_DEPTH {
            let reason = format!("Modules nest deeper than {MAX_MODULE_DEPTH} levels: {rel}");
            self.problems.push(Problem {
                reason,
                file: parent.rel.clone(),
            });
            return;
        }
        let mut module = parent.module.clone();
        for part in child.inline.iter().map(String::as_str).chain([name]) {
            module = format!("{module}.{}", part.trim_start_matches("r#"));
        }
        let module = self.distinct(module);
        // A file that a `path` attribute loads owns its directory, as a `mod.rs` does.
        let mod_rs = path_loaded || rel.ends_with("/mod.rs") || rel == "mod.rs";
        let stem = rel.rsplit('/').next().unwrap_or("").trim_end_matches(".rs");
        let owner = if mod_rs {
            dirname(&rel).to_owned()
        } else {
            join(dirname(&rel), stem)
        };
        queue.push_back(Pending {
            rel,
            module,
            owner,
            depth,
            test,
        });
    }
}

/// The file of `mod name;` and whether a `path` attribute chose it.
fn locate(
    source: &mut Snapshot,
    parent: &Pending,
    child: &Child,
    name: &str,
) -> Result<(String, bool), String> {
    let nested = child
        .inline
        .iter()
        .map(|part| part.trim_start_matches("r#"))
        .collect::<Vec<_>>()
        .join("/");
    if let Some(path) = &child.path {
        let base = join(dirname(&parent.rel), &nested);
        let rel = normalize(&join(&base, path))
            .filter(|rel| source.is_file(rel))
            .ok_or_else(|| {
                format!(
                    "Module file not found: {path} (mod {name} in {})",
                    parent.rel
                )
            })?;
        return Ok((rel, true));
    }
    let base = join(&parent.owner, &nested);
    let flat = normalize(&join(&base, &format!("{name}.rs")));
    let folder = normalize(&join(&base, &format!("{name}/mod.rs")));
    match (
        flat.filter(|rel| source.is_file(rel)),
        folder.filter(|rel| source.is_file(rel)),
    ) {
        (Some(rel), None) | (None, Some(rel)) => Ok((rel, false)),
        (Some(_), Some(_)) => Err(format!(
            "Module file is ambiguous: mod {name} in {}",
            parent.rel
        )),
        (None, None) => Err(format!(
            "Module file not found: mod {name} in {}",
            parent.rel
        )),
    }
}

#[cfg(test)]
#[path = "tree_tests.rs"]
mod tests;
