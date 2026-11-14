// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Whether any file of the snapshot can redirect a dependency to a path (AD-502).
//!
//! Cargo can point a registry name at a local crate: `[patch]` and `[replace]` in a manifest, and
//! `[patch]`, `[replace]`, `paths`, `[source]` or an `include` in a `.cargo/config.toml` (or the
//! old `.cargo/config`). One predicate for the whole scan: if any such file redirects, or does not
//! parse, no dependency is cut from the crates of the workspace (the old rule stays: a name of the
//! workspace is an edge). The price is a false FAIL for a repository that has a patch or a vendored
//! source. A config outside the snapshot (`$CARGO_HOME`, a directory above the repository), the
//! `CARGO_*` environment and `--config` stay unread: `docs/known-limits.md`.

use std::collections::BTreeSet;

use crate::source::read_text;
use crate::toml::{self, Table};
use archkeel_snapshot::paths::{dirname, join};
use archkeel_snapshot::Snapshot;

/// The keys of a manifest that redirect a dependency.
const MANIFEST_KEYS: [&str; 2] = ["patch", "replace"];
/// The keys of a cargo config that redirect a dependency or read another file that may.
const CONFIG_KEYS: [&str; 5] = ["patch", "replace", "paths", "source", "include"];
/// The cargo config files of one directory; both are read.
const CONFIGS: [&str; 2] = [".cargo/config.toml", ".cargo/config"];

/// What the files of the snapshot say.
#[derive(Debug, Default, PartialEq, Eq)]
pub(crate) struct Outcome {
    /// A file redirects or does not parse: a registry name stays an edge to a crate of the
    /// workspace of that name.
    pub redirected: bool,
    /// A file that does not parse and is not reported elsewhere: its path and the reason.
    pub unread: Vec<(String, String)>,
}

fn has(table: &Table, keys: &[&str]) -> bool {
    keys.iter().any(|key| table.contains_key(*key))
}

/// Read the manifests of the directories of `manifests` and of every directory above them, and
/// the cargo configs of the same directories. A manifest in `manifests` is reported by the crate
/// reader when it does not parse; any other file is reported here.
pub(crate) fn scan(source: &mut Snapshot, manifests: &[String]) -> Outcome {
    let mut directories = BTreeSet::new();
    for file in manifests {
        let mut at = dirname(file).to_owned();
        while directories.insert(at.clone()) && !at.is_empty() {
            at = dirname(&at).to_owned();
        }
    }
    let mut found = Outcome::default();
    for dir in directories {
        let manifest = join(&dir, "Cargo.toml");
        let own = manifests.contains(&manifest);
        let files = std::iter::once((manifest, MANIFEST_KEYS.as_slice(), own)).chain(
            CONFIGS
                .iter()
                .map(|name| (join(&dir, name), CONFIG_KEYS.as_slice(), false)),
        );
        for (rel, keys, reported) in files {
            if !source.is_file(&rel) {
                continue;
            }
            let read = read_text(source, &rel)
                .and_then(|text| toml::parse(&text).map_err(|e| format!("Cannot read {rel}: {e}")));
            match read {
                Ok(table) => found.redirected |= has(&table, keys),
                Err(reason) => {
                    found.redirected = true;
                    if !reported {
                        found.unread.push((rel, reason));
                    }
                }
            }
        }
    }
    found
}

#[cfg(test)]
#[path = "redirects_tests.rs"]
mod tests;
