// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Every read of the snapshot goes through here, as through `config.Snapshot`.
//!
//! A read is contained and digested, and the file is never executed. A path that leaves the
//! snapshot, by name or by symlink, is never read.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

use archkeel_wire::identity::sha256_hex;
use archkeel_wire::reply::{Input, Role};

use crate::paths::{is_outside, join, normpath};

pub const OUTSIDE: &str = "Resolver input outside snapshot";
pub const SYMLINK: &str = "Resolver symlink outside snapshot";

pub struct Snapshot {
    root: PathBuf,
    inputs: BTreeMap<String, (String, Role)>,
    // The snapshot does not change during one collection, so each real path is looked up once.
    reals: HashMap<String, Option<String>>,
    /// Problems become collection gaps.
    pub problems: BTreeSet<String>,
}

impl Snapshot {
    pub fn new(root: &str) -> Self {
        let root = fs::canonicalize(root).unwrap_or_else(|_| PathBuf::from(root));
        Self {
            root,
            inputs: BTreeMap::new(),
            reals: HashMap::new(),
            problems: BTreeSet::new(),
        }
    }

    fn absolute(&self, rel: &str) -> PathBuf {
        let mut path = self.root.clone();
        for part in normpath(rel).split('/').filter(|part| *part != ".") {
            if part == ".." {
                path.pop();
            } else {
                path.push(part);
            }
        }
        path
    }

    /// The real snapshot-relative path of an existing entry; `None` when absent or escaping.
    pub fn real(&mut self, rel: &str) -> Option<String> {
        if is_outside(rel) {
            return None;
        }
        if let Some(known) = self.reals.get(rel) {
            return known.clone();
        }
        let real = fs::canonicalize(self.absolute(rel)).ok().and_then(|real| {
            match real.strip_prefix(&self.root) {
                Ok(inside) => Some(relative_text(inside)),
                Err(_) => {
                    self.problems.insert(SYMLINK.to_owned());
                    None
                }
            }
        });
        self.reals.insert(rel.to_owned(), real.clone());
        real
    }

    pub fn is_file(&mut self, rel: &str) -> bool {
        if is_outside(rel) {
            if self.absolute(rel).exists() {
                self.problems.insert(OUTSIDE.to_owned());
            }
            return false;
        }
        self.real(rel)
            .is_some_and(|real| self.absolute(&real).is_file())
    }

    pub fn is_dir(&mut self, rel: &str) -> bool {
        self.real(rel)
            .is_some_and(|real| self.absolute(&real).is_dir())
    }

    /// Read and digest a file; its input role stays the one it already has.
    pub fn read(&mut self, rel: &str) -> Option<Vec<u8>> {
        if !self.is_file(rel) {
            return None;
        }
        match fs::read(self.absolute(rel)) {
            Ok(raw) => {
                let role = self
                    .inputs
                    .get(rel)
                    .map_or(Role::Resolution, |(_, role)| *role);
                self.inputs.insert(rel.to_owned(), (sha256_hex(&raw), role));
                Some(raw)
            }
            Err(_) => {
                self.problems
                    .insert(format!("Unreadable resolver input: {rel}"));
                None
            }
        }
    }

    /// Mark a read file as a selected source file.
    pub fn select(&mut self, rel: &str) {
        if let Some((_, role)) = self.inputs.get_mut(rel) {
            *role = Role::Selected;
        }
    }

    /// Sorted file and directory names; symlinks are followed only inside the snapshot.
    ///
    /// A directory or an entry that cannot be read is a problem, never a silent omission.
    pub fn entries(&mut self, rel: &str) -> (Vec<String>, Vec<String>) {
        let (mut files, mut directories) = (Vec::new(), Vec::new());
        let Some(real) = self.real(rel) else {
            return (files, directories);
        };
        let Ok(listing) = fs::read_dir(self.absolute(&real)) else {
            self.problems
                .insert(format!("Unreadable source directory: {rel}"));
            return (files, directories);
        };
        let mut names = Vec::new();
        for entry in listing {
            let problem = match entry.map(|entry| entry.file_name().into_string()) {
                Ok(Ok(name)) => {
                    names.push(name);
                    continue;
                }
                Ok(Err(raw)) => format!(
                    "Source name is not UTF-8: {}",
                    join(rel, &raw.to_string_lossy())
                ),
                Err(_) => format!("Unreadable source directory: {rel}"),
            };
            self.problems.insert(problem);
        }
        names.sort();
        for name in names {
            let child = join(rel, &name);
            let Some(real) = self.real(&child) else {
                continue;
            };
            match fs::metadata(self.absolute(&real)) {
                Ok(found) if found.is_dir() => directories.push(name),
                Ok(found) if found.is_file() => files.push(name),
                Ok(_) => {}
                Err(_) => {
                    self.problems
                        .insert(format!("Unreadable source entry: {child}"));
                }
            }
        }
        (files, directories)
    }

    /// Whether a path, or its real path, is inside an installed package.
    pub fn installed(&mut self, rel: &str) -> bool {
        let path = self.real(rel).unwrap_or_else(|| rel.to_owned());
        path.split('/').any(|part| part == "node_modules")
    }

    /// The digested inputs, sorted by path.
    pub fn inputs(&self) -> Vec<Input> {
        self.inputs
            .iter()
            .map(|(path, (digest, role))| Input {
                path: path.clone(),
                digest: digest.clone(),
                role: *role,
            })
            .collect()
    }
}

fn relative_text(path: &Path) -> String {
    let parts: Vec<String> = path
        .components()
        .map(|part| part.as_os_str().to_string_lossy().into_owned())
        .collect();
    if parts.is_empty() {
        ".".to_owned()
    } else {
        parts.join("/")
    }
}

#[cfg(test)]
#[path = "snapshot_tests.rs"]
mod tests;
