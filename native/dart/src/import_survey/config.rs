// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package configuration that `pub get` writes (AD-454): `.dart_tool/package_config.json`.
//! Dart resolves each `package:` URI with it, so the survey reads it when it exists.
//!
//! - Absent: no `pub get` ran yet. The language maps the own package to `lib/`, as the survey does.
//! - Present: the own package must have `rootUri` at the snapshot root and `packageUri` `lib/`.
//!   Another package must not map into the snapshot root: then its files are not external.
//! - A link, an unreadable or malformed file, or an entry that the survey cannot place is a gap.

use std::path::Path;

use archkeel_facts::envelope::{Input, Role};
use archkeel_facts::identity::sha256_hex;
use archkeel_snapshot::paths::{is_outside, join, normpath};
use archkeel_snapshot::Snapshot;
use serde_json::Value;

use super::names::{GapName, Gaps, Place};

pub(crate) const CONFIG: &str = ".dart_tool/package_config.json";

/// Check the configuration of `snapshot` for the own package `own`. Give its input when it is read.
pub(crate) fn config_gaps(
    snapshot: &mut Snapshot,
    root: &str,
    own: &str,
    gaps: &mut Gaps,
) -> Option<Input> {
    if !snapshot.is_link(CONFIG) && !snapshot.is_file(CONFIG) && !snapshot.is_link(".dart_tool") {
        return None;
    }
    let raw = (!snapshot.is_link(CONFIG) && !snapshot.is_link(".dart_tool"))
        .then(|| snapshot.read(CONFIG))
        .flatten();
    let Some(raw) = raw else {
        let message = "the package configuration is a link or cannot be read";
        gaps.named(GapName::DartPackageConfig, Place::File(CONFIG), message);
        return None;
    };
    if let Err(message) = check(&raw, root, own) {
        gaps.named(GapName::DartPackageConfig, Place::File(CONFIG), &message);
    }
    Some(Input {
        digest: sha256_hex(&raw),
        path: CONFIG.to_owned(),
        role: Role::Resolution,
    })
}

/// `Ok` when the configuration keeps the own package at `lib/` and no other package inside `root`.
fn check(raw: &[u8], root: &str, own: &str) -> Result<(), String> {
    let value: Value = serde_json::from_slice(raw)
        .map_err(|error| format!("the package configuration is not JSON: {error}"))?;
    let packages = value
        .get("packages")
        .and_then(Value::as_array)
        .ok_or("the package configuration has no packages list")?;
    let mut own_found = false;
    for entry in packages {
        let name = entry.get("name").and_then(Value::as_str);
        let root_uri = entry.get("rootUri").and_then(Value::as_str);
        let (Some(name), Some(root_uri)) = (name, root_uri) else {
            return Err("a package entry has no name or no rootUri".to_owned());
        };
        let place = place(root_uri, root);
        if name == own {
            own_found = true;
            let package_uri = entry
                .get("packageUri")
                .and_then(Value::as_str)
                .unwrap_or("");
            let lib = normpath(package_uri) == "lib";
            if place != Location::Root || !lib {
                return Err(format!(
                    "the own package {own} is not mapped to lib/ of this root"
                ));
            }
        } else if place != Location::Outside {
            return Err(format!(
                "the package {name} is mapped into this root or to an unknown place"
            ));
        }
    }
    if own_found || own.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "the package configuration does not list the own package {own}"
        ))
    }
}

/// Where a `rootUri` points, seen from the snapshot root.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Location {
    /// The snapshot root itself.
    Root,
    /// Below the snapshot root.
    Inside,
    /// Outside the snapshot root.
    Outside,
    /// A form that the survey does not read: another scheme or an escape.
    Unknown,
}

/// The place of `uri`: a path relative to `.dart_tool/` or a `file:` URI.
fn place(uri: &str, root: &str) -> Location {
    if uri.contains(['%', '\\', '?', '#']) {
        return Location::Unknown;
    }
    if let Some(path) = uri.strip_prefix("file://") {
        return absolute(path, root);
    }
    if uri.contains(':') || uri.starts_with('/') {
        return Location::Unknown;
    }
    let joined = join(".dart_tool", uri);
    if joined == "." {
        Location::Root
    } else if is_outside(&joined) {
        Location::Outside
    } else {
        Location::Inside
    }
}

/// The place of an absolute path, compared with the root as written and with real paths.
fn absolute(path: &str, root: &str) -> Location {
    let roots: Vec<String> = [Some(normpath(root)), real(root)]
        .into_iter()
        .flatten()
        .collect();
    let candidates: Vec<String> = [Some(normpath(path)), real(path)]
        .into_iter()
        .flatten()
        .collect();
    for candidate in &candidates {
        for base in &roots {
            if candidate == base {
                return Location::Root;
            }
            if candidate.starts_with(&format!("{base}/")) {
                return Location::Inside;
            }
        }
    }
    Location::Outside
}

/// The real path of `path`: the real path of its longest existing ancestor and the rest.
fn real(path: &str) -> Option<String> {
    let mut head = Path::new(path);
    let mut rest = Vec::new();
    loop {
        if let Ok(found) = head.canonicalize() {
            let mut found = found;
            found.extend(rest.iter().rev());
            return found.to_str().map(normpath);
        }
        rest.push(head.file_name()?.to_owned());
        head = head.parent()?;
    }
}
