// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Every read of the snapshot goes through here. A read is digested and the file is never
//! executed. A symbolic link is never followed: a link can point outside the snapshot.

use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::Read;
use std::path::PathBuf;

use archkeel_wire::identity::sha256_hex;
use archkeel_wire::reply::{Input, Role};

/// The largest file that the collector reads (AD-319). A larger Rust file is generated or hostile.
pub const MAX_FILE_BYTES: u64 = 4 * 1024 * 1024;
/// The deepest directory that the walk enters.
const MAX_DEPTH: usize = 128;

pub struct Source {
    root: PathBuf,
    inputs: BTreeMap<String, (String, Role)>,
}

impl Source {
    pub fn new(root: &str) -> Self {
        Self {
            root: fs::canonicalize(root).unwrap_or_else(|_| PathBuf::from(root)),
            inputs: BTreeMap::new(),
        }
    }

    fn absolute(&self, rel: &str) -> PathBuf {
        rel.split('/')
            .filter(|part| !part.is_empty())
            .fold(self.root.clone(), |path, part| path.join(part))
    }

    pub fn is_file(&self, rel: &str) -> bool {
        fs::symlink_metadata(self.absolute(rel)).is_ok_and(|meta| meta.file_type().is_file())
    }

    pub fn is_dir(&self, rel: &str) -> bool {
        fs::symlink_metadata(self.absolute(rel)).is_ok_and(|meta| meta.file_type().is_dir())
    }

    /// Read a file as text. The reason of a failure names the file.
    pub fn read(&mut self, rel: &str, role: Role) -> Result<String, String> {
        let path = self.absolute(rel);
        let meta = fs::symlink_metadata(&path).map_err(|_| format!("Unreadable file: {rel}"))?;
        if meta.file_type().is_symlink() {
            return Err(format!("A symbolic link is not read: {rel}"));
        }
        if meta.len() > MAX_FILE_BYTES {
            return Err(format!("File is larger than {MAX_FILE_BYTES} bytes: {rel}"));
        }
        let mut bytes = Vec::new();
        File::open(&path)
            .and_then(|file| file.take(MAX_FILE_BYTES).read_to_end(&mut bytes))
            .map_err(|_| format!("Unreadable file: {rel}"))?;
        let entry = self.inputs.entry(rel.to_owned());
        let digest = sha256_hex(&bytes);
        let known = entry.or_insert_with(|| (digest, role));
        if role == Role::Selected {
            known.1 = Role::Selected;
        }
        Ok(String::from_utf8_lossy(&bytes).into_owned())
    }

    /// The files below `rel`, relative to the snapshot, sorted. A directory named `target`, a
    /// hidden directory and a symbolic link are not entered.
    pub fn walk(&self, rel: &str) -> Vec<String> {
        let mut found = Vec::new();
        self.walk_into(rel, 0, &mut found);
        found.sort();
        found
    }

    fn walk_into(&self, rel: &str, depth: usize, found: &mut Vec<String>) {
        if depth > MAX_DEPTH {
            return;
        }
        let Ok(entries) = fs::read_dir(self.absolute(rel)) else {
            return;
        };
        for entry in entries.flatten() {
            let Ok(kind) = entry.file_type() else {
                continue;
            };
            let name = entry.file_name().to_string_lossy().into_owned();
            let child = if rel.is_empty() || rel == "." {
                name.clone()
            } else {
                format!("{rel}/{name}")
            };
            if kind.is_dir() && name != "target" && !name.starts_with('.') {
                self.walk_into(&child, depth + 1, found);
            } else if kind.is_file() {
                found.push(child);
            }
        }
    }

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

#[cfg(test)]
#[path = "source_tests.rs"]
mod tests;
