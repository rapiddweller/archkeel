// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module tree of each crate: from the file of a target, through each `mod name;`.
//!
//! `syn` parses a file, not a crate, so the walk follows the `mod` declarations itself. A file
//! that is in no tree is not guessed to belong to a crate: the caller reports it as UNKNOWN.

use std::collections::{BTreeSet, VecDeque};

use archkeel_wire::reply::Role;

use crate::crates::{Crate, Problem, Root, Workspace};
use crate::paths::{dirname, join, normalize};
use crate::scan::{scan, Child, Scan};
use crate::source::Source;

/// One file of a module tree, read and scanned.
pub struct Module {
    pub rel: String,
    pub module: String,
    pub crate_index: usize,
    pub text: String,
    pub scan: Scan,
}

pub struct Walked {
    pub modules: Vec<Module>,
    pub problems: Vec<Problem>,
    /// The files that no module tree reaches are those of `files` that are not here.
    pub claimed: BTreeSet<String>,
}

/// A file that waits for its scan.
struct Pending {
    rel: String,
    module: String,
    /// The directory where the `mod` declarations of this file look for their files.
    owner: String,
}

pub fn walk(source: &mut Source, workspace: &Workspace) -> Walked {
    let mut walked = Walked {
        modules: Vec::new(),
        problems: Vec::new(),
        claimed: BTreeSet::new(),
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
    fn start(&mut self, source: &mut Source, index: usize, krate: &Crate, root: &Root) {
        if self.claimed.insert(root.rel.clone()) {
            let first = Pending {
                rel: root.rel.clone(),
                module: root.module.clone(),
                owner: dirname(&root.rel).to_owned(),
            };
            self.crate_tree(source, index, krate, first);
        }
    }

    fn crate_tree(&mut self, source: &mut Source, index: usize, krate: &Crate, first: Pending) {
        let mut queue = VecDeque::from([first]);
        while let Some(file) = queue.pop_front() {
            let text = match source.read(&file.rel, Role::Selected) {
                Ok(text) => text,
                Err(reason) => {
                    self.problems.push(Problem {
                        reason,
                        file: file.rel,
                    });
                    continue;
                }
            };
            let scanned = scan(&text, &krate.manifest.features).unwrap_or_else(|error| {
                let reason = format!("Syntax error in {}: {error}", file.rel);
                self.problems.push(Problem {
                    reason,
                    file: file.rel.clone(),
                });
                Scan::default()
            });
            for child in &scanned.children {
                self.child(source, &file, child, &mut queue);
            }
            self.modules.push(Module {
                rel: file.rel,
                module: file.module,
                crate_index: index,
                text,
                scan: scanned,
            });
        }
    }

    fn child(
        &mut self,
        source: &Source,
        parent: &Pending,
        child: &Child,
        queue: &mut VecDeque<Pending>,
    ) {
        let name = child.name.trim_start_matches("r#");
        let found = locate(source, parent, child, name);
        let (rel, path_loaded) = match found {
            Ok(found) => found,
            Err(reason) => {
                self.problems.push(Problem {
                    reason,
                    file: parent.rel.clone(),
                });
                return;
            }
        };
        if !self.claimed.insert(rel.clone()) {
            let reason = format!("The file {rel} is the file of two modules");
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
        // A file that a `path` attribute loads owns its directory, as a `mod.rs` does.
        let mod_rs = path_loaded || rel.ends_with("/mod.rs") || rel == "mod.rs";
        let stem = rel.rsplit('/').next().unwrap_or("").trim_end_matches(".rs");
        let owner = if mod_rs {
            dirname(&rel).to_owned()
        } else {
            join(dirname(&rel), stem)
        };
        queue.push_back(Pending { rel, module, owner });
    }
}

/// The file of `mod name;` and whether a `path` attribute chose it.
fn locate(
    source: &Source,
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
