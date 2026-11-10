// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Which part of a snapshot is an installed package. This is a rule of TypeScript, so it is not
//! part of `archkeel-snapshot`.

use archkeel_snapshot::Snapshot;

/// Whether a path, or its real path, is inside an installed package (`node_modules`).
pub fn installed(snapshot: &mut Snapshot, rel: &str) -> bool {
    let path = snapshot.real(rel).unwrap_or_else(|| rel.to_owned());
    path.split('/').any(|part| part == "node_modules")
}

#[cfg(test)]
#[path = "installed_tests.rs"]
mod tests;
