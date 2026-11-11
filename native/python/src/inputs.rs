// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The digested inputs of a survey and its source digest, as `collect._inputs` gives them.
//!
//! The inputs are the selected files and `pyproject.toml` when it is a file inside the snapshot.
//! The source digest is SHA-256 over `path \0 bytes \0` of each input, in the order of the paths.
//! A file that cannot be read is no input; the snapshot cannot read a file over 4 MiB (AD-319).

use archkeel_facts::envelope::{Input, Role};
use archkeel_facts::identity::sha256_hex;
use archkeel_snapshot::Snapshot;
use sha2::{Digest, Sha256};

pub const PYPROJECT: &str = "pyproject.toml";

/// The inputs, sorted by path, and the source digest.
pub fn inputs(snapshot: &mut Snapshot, selected: &[String]) -> (Vec<Input>, String) {
    let mut paths: Vec<(&str, Role)> = selected
        .iter()
        .map(|rel| (rel.as_str(), Role::Selected))
        .collect();
    if snapshot.is_file(PYPROJECT) {
        paths.push((PYPROJECT, Role::Resolution));
    }
    paths.sort_by(|left, right| left.0.cmp(right.0));
    let mut source = Sha256::new();
    let mut found = Vec::new();
    for (rel, role) in paths {
        let Some(raw) = snapshot.read(rel) else {
            continue;
        };
        found.push(Input {
            digest: sha256_hex(&raw),
            path: rel.to_owned(),
            role,
        });
        source.update(rel.as_bytes());
        source.update(b"\0");
        source.update(&raw);
        source.update(b"\0");
    }
    let digest = source
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    (found, digest)
}

#[cfg(test)]
#[path = "inputs_tests.rs"]
mod tests;
