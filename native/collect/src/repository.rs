// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reads of the scan identity in the repository (AD-406): the configuration, the contract and
//! the inside contracts, the Git head, and the survey that bounds the work of the collector.
//!
//! A path resolves inside the repository root or is refused: `..`, an absolute path and a symlink
//! out of the root give no bytes. The root comes from the caller; nothing here reads an
//! environment variable, `PATH` or a directory beside the binary.

use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};

/// The largest configuration file that the core reads.
pub(crate) const MAX_CONFIG_BYTES: u64 = 1 << 20;
/// The work budget of the survey: the most directory entries below the root (AD-406, #1099).
pub(crate) const MAX_ENTRIES: usize = 100_000;
/// The most directory entries below the proven cache directories of the root (AD-432).
pub(crate) const MAX_CACHE_ENTRIES: usize = 1_000_000;
/// The deepest directory below the root that the survey enters.
pub(crate) const MAX_DEPTH: usize = 256;
/// The most bytes of all regular files below the root.
pub(crate) const MAX_TOTAL_BYTES: u64 = 1 << 30;

/// The repository root: a canonical absolute directory.
#[derive(Debug)]
pub(crate) struct Root(PathBuf);

impl Root {
    /// The root of `text`. It must be absolute and canonical, as the shell resolves it, so the
    /// root of the request and the snapshot root of the collector are one path.
    pub(crate) fn of(text: &str) -> Result<Root, String> {
        let path = Path::new(text);
        if !path.is_absolute() {
            return Err(format!("the root {text} is not an absolute path"));
        }
        let canonical = fs::canonicalize(path)
            .map_err(|error| format!("the root {text} cannot be resolved: {error}"))?;
        // The text, not the `Path`: `Path` equality skips a `.` part.
        if canonical.as_os_str() != path.as_os_str() {
            return Err(format!(
                "the root {text} is not canonical; it resolves to {}",
                canonical.display()
            ));
        }
        if !canonical.is_dir() {
            return Err(format!("the root {text} is not a directory"));
        }
        Ok(Root(canonical))
    }

    pub(crate) fn path(&self) -> &Path {
        &self.0
    }

    /// The real path of `relative` when it resolves inside the root, else `None`.
    pub(crate) fn contained(&self, relative: &str) -> Option<PathBuf> {
        let target = fs::canonicalize(self.0.join(relative)).ok()?;
        target.starts_with(&self.0).then_some(target)
    }

    /// The repository-relative POSIX path of a contained real path.
    pub(crate) fn identity(&self, target: &Path) -> Option<String> {
        let rest = target.strip_prefix(&self.0).ok()?;
        let parts: Option<Vec<&str>> = rest
            .components()
            .map(|part| match part {
                Component::Normal(name) => name.to_str(),
                _ => None,
            })
            .collect();
        Some(parts?.join("/"))
    }

    /// `read_inside` of the shell: the identity and the bytes of a contained file, `None` when
    /// the path is missing, not a file or outside the root, and an error over `budget` bytes.
    pub(crate) fn read(
        &self,
        relative: &str,
        budget: u64,
    ) -> Result<Option<(String, Vec<u8>)>, Over> {
        let Some(target) = self.contained(relative) else {
            return Ok(None);
        };
        let Some(identity) = self.identity(&target) else {
            return Ok(None);
        };
        if !target.is_file() {
            return Ok(None);
        }
        let Ok(file) = fs::File::open(&target) else {
            return Ok(None);
        };
        let mut bytes = Vec::new();
        if file
            .take(budget.saturating_add(1))
            .read_to_end(&mut bytes)
            .is_err()
        {
            return Ok(None);
        }
        if bytes.len() as u64 > budget {
            return Err(Over(relative.to_owned()));
        }
        Ok(Some((identity, bytes)))
    }

    /// `load_config`: the path is a contained directory, or a file when `file_too`.
    pub(crate) fn is_dir_or_file(&self, relative: &str, file_too: bool) -> bool {
        self.contained(relative)
            .is_some_and(|target| target.is_dir() || (file_too && target.is_file()))
    }

    /// `load_config`: the path is a contained file.
    pub(crate) fn is_file(&self, relative: &str) -> bool {
        self.contained(relative)
            .is_some_and(|target| target.is_file())
    }
}

/// A file over the byte budget of its read.
#[derive(Debug, PartialEq, Eq)]
pub struct Over(pub String);

/// The name of a cache directory tag (<https://bford.info/cachedir/>), and how its text starts.
/// Cargo writes the tag into each target directory; other build tools write it into their caches.
const CACHE_TAG: &str = "CACHEDIR.TAG";
const CACHE_SIGNATURE: [u8; 43] = *b"Signature: 8a477f597d28d172789f06886806bc55";

/// Whether a tag proves `directory` as a cache: a regular file, not a link, with the signature.
fn is_cache(directory: &Path) -> bool {
    let tag = directory.join(CACHE_TAG);
    let mut start = [0u8; CACHE_SIGNATURE.len()];
    fs::symlink_metadata(&tag).is_ok_and(|data| data.is_file())
        && fs::File::open(&tag)
            .and_then(|mut file| file.read_exact(&mut start))
            .is_ok()
        && start == CACHE_SIGNATURE
}

/// The work budget of a collection: each directory entry below the root is charged one unit,
/// without following a symlink and without `.git`. A root over the count, the depth or the byte
/// total is refused by name, so the collector never starts on it.
///
/// The files below a proven cache directory are build output (AD-432). Their depth is charged, and
/// their entries are charged to a budget of their own, because a collector can list them and a
/// used build directory holds more entries than the source. Their bytes are not charged: the
/// snapshot charges each byte that a collector reads there (AD-420). The survey selects no
/// source, so this rule cannot remove a file from a scan.
pub(crate) fn survey(root: &Root) -> Result<(), String> {
    survey_within(root, MAX_CACHE_ENTRIES)
}

/// The survey with a stated budget for the entries below the proven cache directories.
fn survey_within(root: &Root, cache_entries: usize) -> Result<(), String> {
    let mut stack: Vec<(PathBuf, usize, bool)> = vec![(root.path().to_path_buf(), 0, false)];
    let (mut entries, mut cached, mut bytes) = (0usize, 0usize, 0u64);
    while let Some((directory, depth, inherited)) = stack.pop() {
        if depth > MAX_DEPTH {
            return Err(format!(
                "the repository has a directory deeper than {MAX_DEPTH} levels"
            ));
        }
        let cache = inherited || is_cache(&directory);
        let listing = fs::read_dir(&directory)
            .map_err(|error| format!("cannot list {}: {error}", directory.display()))?;
        for entry in listing {
            if cache {
                cached = cached.saturating_add(1);
            } else {
                entries = entries.saturating_add(1);
            }
            if entries > MAX_ENTRIES {
                return Err(format!(
                    "the repository has more than {MAX_ENTRIES} entries, the work budget of \
                     the collector in the core process"
                ));
            }
            if cached > cache_entries {
                return Err(format!(
                    "the repository has more than {cache_entries} entries below its cache \
                     directories, the work budget of the collector in the core process"
                ));
            }
            let entry =
                entry.map_err(|error| format!("cannot list {}: {error}", directory.display()))?;
            let Ok(kind) = entry.file_type() else {
                continue;
            };
            if kind.is_dir() && entry.file_name() != ".git" {
                stack.push((entry.path(), depth.saturating_add(1), cache));
            } else if kind.is_file() && !cache {
                bytes = charged(bytes, entry.metadata().map_or(0, |data| data.len()))?;
            }
        }
    }
    Ok(())
}

/// The byte total after one more file, or the refusal over `MAX_TOTAL_BYTES`.
fn charged(total: u64, size: u64) -> Result<u64, String> {
    let total = total.saturating_add(size);
    if total > MAX_TOTAL_BYTES {
        return Err(format!(
            "the repository holds more than {MAX_TOTAL_BYTES} bytes of files"
        ));
    }
    Ok(total)
}

#[cfg(test)]
#[path = "repository_tests.rs"]
pub(crate) mod tests;
