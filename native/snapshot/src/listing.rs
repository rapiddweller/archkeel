// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A directory listing that does not follow a symbolic link.
//!
//! `Snapshot::entries` follows a link that stays inside the snapshot, as the TypeScript collector
//! does. The Dart collector follows no link: it names each link as a gap. This listing gives it
//! each link as a link, so the symlink rule stays in this crate.

use std::fs;

use super::Snapshot;
use crate::paths::{is_outside, join};

/// The kind of one entry of a listing.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Entry {
    File,
    Directory,
    /// A symbolic link. `to_directory` is true when its target is a directory, so a walk can sort
    /// the link with the directories or with the files, as `os.walk` does.
    Link {
        to_directory: bool,
    },
    /// A socket, a pipe or a device.
    Other,
}

impl Snapshot {
    /// The sorted entries of the directory `rel`, without following a link.
    ///
    /// `None` when `rel` is outside the snapshot or cannot be read; a read failure is a problem.
    pub fn listing(&mut self, rel: &str) -> Option<Vec<(String, Entry)>> {
        if is_outside(rel) {
            return None;
        }
        let Ok(listing) = fs::read_dir(self.absolute(rel)) else {
            self.problems
                .insert(format!("Unreadable source directory: {rel}"));
            return None;
        };
        let mut entries = Vec::new();
        for entry in listing {
            let name = match entry.map(|entry| entry.file_name().into_string()) {
                Ok(Ok(name)) => name,
                Ok(Err(raw)) => {
                    let child = join(rel, &raw.to_string_lossy());
                    self.problems
                        .insert(format!("Source name is not UTF-8: {child}"));
                    continue;
                }
                Err(_) => {
                    self.problems
                        .insert(format!("Unreadable source directory: {rel}"));
                    continue;
                }
            };
            let kind = self.kind(&join(rel, &name));
            entries.push((name, kind));
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

    fn kind(&self, rel: &str) -> Entry {
        let path = self.absolute(rel);
        match fs::symlink_metadata(&path) {
            Ok(found) if found.file_type().is_symlink() => Entry::Link {
                to_directory: fs::metadata(&path).is_ok_and(|target| target.is_dir()),
            },
            Ok(found) if found.is_dir() => Entry::Directory,
            Ok(found) if found.is_file() => Entry::File,
            _ => Entry::Other,
        }
    }
}

#[cfg(test)]
#[path = "listing_tests.rs"]
mod tests;
