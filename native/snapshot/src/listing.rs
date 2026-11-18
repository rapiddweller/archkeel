// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A walk of the snapshot that does not follow a symbolic link.
//!
//! `Snapshot::entries` and `Snapshot::read` follow a link that stays inside the snapshot, as the
//! TypeScript collector does, and resolve the real path of each file. The Dart collector follows
//! no link: it names each link as a gap. This walk gives it each link as a link, so the symlink
//! rule stays in this crate.
//!
//! Containment: `check_root` resolves the real path of a scan root once and requires a directory
//! inside the snapshot. `listing` marks each real directory below a checked root as walked; a
//! link is never walked. `read_walked` reads only a file whose parent is walked, so no part of
//! its path is a link. It compares the file before and after the open, as the `samestat` check of
//! the Python collector does, so a file that changes into a link is not read.

use std::fs::{self, File, Metadata};
use std::io::{ErrorKind, Read};

use archkeel_facts::envelope::Role;
use archkeel_facts::identity::sha256_hex;

use super::{Snapshot, MAX_FILE_BYTES};
use crate::paths::{dirname, is_outside, join};

const MAX_LISTING_ENTRIES: usize = 1_000_000;

/// The kind of one entry of a listing.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Entry {
    /// A regular file.
    File,
    /// A directory.
    Directory,
    /// A symbolic link. `to_directory` is true when its target is a directory, so a walk can sort
    /// the link with the directories or with the files, as `os.walk` does.
    Link {
        /// True when the target of the link is a directory.
        to_directory: bool,
    },
    /// A socket, a pipe or a device.
    Other,
}

/// The result of the check of one scan root.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RootCheck {
    /// A directory inside the snapshot, and not a link: the walk can start here.
    Contained,
    /// A root that is a symbolic link: the walk does not follow it.
    Link,
    /// Missing, or not a directory.
    NotDirectory,
    /// The real path of the root is outside the snapshot.
    Escapes,
}

impl Snapshot {
    /// Check the scan root `rel` once, with its real path. A contained root starts a walk.
    pub fn check_root(&mut self, rel: &str) -> RootCheck {
        if is_outside(rel) {
            return RootCheck::Escapes;
        }
        let path = self.absolute(rel);
        if fs::symlink_metadata(&path).is_ok_and(|found| found.file_type().is_symlink()) {
            return RootCheck::Link;
        }
        let Ok(real) = fs::canonicalize(&path) else {
            return RootCheck::NotDirectory;
        };
        if !real.is_dir() {
            RootCheck::NotDirectory
        } else if !real.starts_with(&self.root) {
            RootCheck::Escapes
        } else {
            self.walked.insert(rel.to_owned());
            RootCheck::Contained
        }
    }

    /// The sorted entries of the directory `rel`, without following a link.
    ///
    /// `None` when `rel` is outside the snapshot, cannot be read, or exceeds the entry limit.
    /// When `rel` is walked, each real subdirectory becomes walked too.
    pub fn listing(&mut self, rel: &str) -> Option<Vec<(String, Entry)>> {
        self.listing_at_most(rel, MAX_LISTING_ENTRIES)
    }

    fn listing_at_most(&mut self, rel: &str, limit: usize) -> Option<Vec<(String, Entry)>> {
        if is_outside(rel) {
            return None;
        }
        let Ok(listing) = fs::read_dir(self.absolute(rel)) else {
            self.problems
                .insert(format!("Unreadable source directory: {rel}"));
            return None;
        };
        let mut entries = Vec::new();
        for (index, entry) in listing.enumerate() {
            if index == limit {
                self.problems
                    .insert(format!("Source directory exceeds the entry limit: {rel}"));
                return None;
            }
            let entry = match entry {
                Ok(entry) => entry,
                Err(_) => {
                    self.problems
                        .insert(format!("Unreadable source directory: {rel}"));
                    return None;
                }
            };
            let name = match entry.file_name().into_string() {
                Ok(name) => name,
                Err(raw) => {
                    let child = join(rel, &raw.to_string_lossy());
                    self.problems
                        .insert(format!("Source name is not UTF-8: {child}"));
                    return None;
                }
            };
            let kind = match entry_kind(&entry) {
                Ok(kind) => kind,
                Err(message) => {
                    let child = join(rel, &name);
                    self.problems.insert(format!("{message}: {child}"));
                    return None;
                }
            };
            entries.push((name, kind));
        }
        if self.walked.contains(rel) {
            self.walked.extend(
                entries
                    .iter()
                    .filter(|(_, kind)| *kind == Entry::Directory)
                    .map(|(name, _)| join(rel, name)),
            );
        }
        entries.sort_by(|a, b| a.0.cmp(&b.0));
        Some(entries)
    }

    /// Whether `rel` is a symbolic link inside the snapshot.
    pub fn is_link(&self, rel: &str) -> bool {
        !is_outside(rel)
            && fs::symlink_metadata(self.absolute(rel))
                .is_ok_and(|found| found.file_type().is_symlink())
    }

    /// Read and digest a regular file of a walked directory, without a real-path lookup.
    ///
    /// `None` when the parent is not walked, the file is a link or not a regular file, changed
    /// during the open, or cannot be read: each is a problem. A file over `MAX_FILE_BYTES` gives
    /// `None`, and `size_gap` names it.
    pub fn read_walked(&mut self, rel: &str) -> Option<Vec<u8>> {
        let parent = match dirname(rel) {
            "" => ".",
            parent => parent,
        };
        if is_outside(rel) || !self.walked.contains(parent) {
            self.problems
                .insert(format!("Source outside a checked root: {rel}"));
            return None;
        }
        let path = self.absolute(rel);
        let opened = fs::symlink_metadata(&path).and_then(|before| {
            let file = File::open(&path)?;
            let after = file.metadata()?;
            Ok((before, after, file))
        });
        let mut file = match opened {
            Ok((before, after, file)) if before.is_file() && same_file(&before, &after) => file,
            Ok(_) => {
                self.problems
                    .insert(format!("Source is not a regular file: {rel}"));
                return None;
            }
            Err(_) => {
                self.problems
                    .insert(format!("Unreadable source file: {rel}"));
                return None;
            }
        };
        let mut raw = Vec::new();
        if file
            .by_ref()
            .take(MAX_FILE_BYTES + 1)
            .read_to_end(&mut raw)
            .is_err()
        {
            self.problems
                .insert(format!("Unreadable source file: {rel}"));
            return None;
        }
        if raw.len() as u64 > MAX_FILE_BYTES {
            self.oversized.insert(rel.to_owned());
            return None;
        }
        if !crate::work::permits(&self.root, rel, &raw) {
            return None;
        }
        self.inputs
            .insert(rel.to_owned(), (sha256_hex(&raw), Role::Selected));
        Some(raw)
    }
}

fn entry_kind(entry: &fs::DirEntry) -> Result<Entry, &'static str> {
    let kind = entry.file_type().map_err(|_| "Unreadable source entry")?;
    if kind.is_symlink() {
        let to_directory = match fs::metadata(entry.path()) {
            Ok(target) => target.is_dir(),
            Err(error) if error.kind() == ErrorKind::NotFound => false,
            Err(_) => return Err("Unreadable link target"),
        };
        Ok(Entry::Link { to_directory })
    } else if kind.is_dir() {
        Ok(Entry::Directory)
    } else if kind.is_file() {
        Ok(Entry::File)
    } else {
        Ok(Entry::Other)
    }
}

/// The metadata before and after the open name one file.
#[cfg(unix)]
fn same_file(before: &Metadata, after: &Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    after.is_file() && before.dev() == after.dev() && before.ino() == after.ino()
}

/// Windows has no stable inode in `std`: the open file must still be a regular file, and the
/// `lstat` before it showed no link.
#[cfg(not(unix))]
fn same_file(_before: &Metadata, after: &Metadata) -> bool {
    after.is_file()
}

#[cfg(test)]
#[path = "listing_tests.rs"]
mod tests;
