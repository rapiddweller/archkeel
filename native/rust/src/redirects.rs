// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Cargo files of the snapshot that do not parse (AD-502, #946). Cargo reads a manifest above a
//! crate and each `.cargo/config.toml` (or the old `.cargo/config`) of its directory and of each
//! directory above it. A file that the reader cannot parse may set what the scan does not see, so
//! it is a named gap. A redirect itself needs no file here: each registry or git name of a crate of
//! the workspace is a pair gap (`edges.rs`), because a redirect can also come from outside the
//! repository.

use std::collections::BTreeSet;

use crate::source::read_text;
use crate::toml;
use archkeel_snapshot::paths::{dirname, join};
use archkeel_snapshot::Snapshot;

const CONFIGS: [&str; 2] = [".cargo/config.toml", ".cargo/config"];

/// Each file that does not parse, with its reason. A manifest of a scanned crate is left out: the
/// crate reader names its parse error.
pub(crate) fn unread(source: &mut Snapshot, manifests: &[String]) -> Vec<(String, String)> {
    let mut directories = BTreeSet::new();
    for file in manifests {
        let mut at = dirname(file).to_owned();
        while directories.insert(at.clone()) && !at.is_empty() {
            at = dirname(&at).to_owned();
        }
    }
    let mut found = Vec::new();
    for dir in directories {
        let manifest = join(&dir, "Cargo.toml");
        let files = std::iter::once(manifest.clone())
            .filter(|_| !manifests.contains(&manifest))
            .chain(CONFIGS.iter().map(|name| join(&dir, name)));
        for rel in files {
            if !source.is_file(&rel) {
                continue;
            }
            let read = read_text(source, &rel)
                .and_then(|text| toml::parse(&text).map_err(|e| format!("Cannot read {rel}: {e}")));
            if let Err(reason) = read {
                found.push((rel, reason));
            }
        }
    }
    found
}

#[cfg(test)]
#[path = "redirects_tests.rs"]
mod tests;
