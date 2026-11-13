// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The commit of `HEAD`, read from the Git directory without a `git` process (AD-406).
//!
//! The core starts no process, so `PATH` cannot select a program. It reads `HEAD`, the loose ref
//! and `packed-refs` of the repository that holds the root, also of a linked work tree (`.git` is
//! then a file with `gitdir:` and the Git directory has `commondir`). Any other form (a symbolic
//! ref chain, a ref that is in no file) is an error, never a guess.

use std::fs;
use std::path::{Path, PathBuf};

/// The longest file of the Git directory that the core reads.
const MAX_GIT_FILE: u64 = 64 << 20;

/// The commit id of `HEAD` of the repository that holds `root`.
pub fn head(root: &Path) -> Result<String, String> {
    let git = git_directory(root)?;
    let common = match small(&git.join("commondir")) {
        Some(text) => git.join(text.trim()),
        None => git.clone(),
    };
    let head = small(&git.join("HEAD")).ok_or("the Git directory has no HEAD")?;
    let head = head.trim_end_matches(['\n', '\r']);
    let Some(name) = head.strip_prefix("ref: ") else {
        return commit(head);
    };
    if !name.starts_with("refs/") || name.split('/').any(|part| part == ".." || part.is_empty()) {
        return Err(format!("HEAD names the unsafe ref {name}"));
    }
    for directory in [&git, &common] {
        if let Some(text) = small(&directory.join(name)) {
            return commit(text.trim_end_matches(['\n', '\r']));
        }
    }
    let packed = small(&common.join("packed-refs")).unwrap_or_default();
    for line in packed.lines() {
        if let Some((id, reference)) = line.split_once(' ') {
            if reference == name {
                return commit(id);
            }
        }
    }
    Err(format!(
        "the ref {name} of HEAD is in no file of the Git directory"
    ))
}

/// The Git directory of the repository that holds `root`: the first `.git` of the root or a
/// parent directory.
fn git_directory(root: &Path) -> Result<PathBuf, String> {
    for directory in root.ancestors() {
        let dot = directory.join(".git");
        if dot.is_dir() {
            return Ok(dot);
        }
        if dot.is_file() {
            let text = small(&dot).ok_or("the .git file cannot be read")?;
            let target = text
                .trim_end_matches(['\n', '\r'])
                .strip_prefix("gitdir: ")
                .ok_or("the .git file has no gitdir line")?;
            return Ok(directory.join(target));
        }
    }
    Err(format!("{} is in no Git repository", root.display()))
}

/// A commit id: 40 or 64 lowercase hexadecimal digits.
fn commit(text: &str) -> Result<String, String> {
    let hex = text
        .bytes()
        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte));
    if hex && matches!(text.len(), 40 | 64) {
        Ok(text.to_owned())
    } else {
        Err(format!("HEAD does not name a commit id: {text}"))
    }
}

/// The text of a small regular file, or `None`.
fn small(path: &Path) -> Option<String> {
    let data = fs::metadata(path).ok()?;
    if !data.is_file() || data.len() > MAX_GIT_FILE {
        return None;
    }
    fs::read_to_string(path).ok()
}
