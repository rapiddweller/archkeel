// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package gaps of the survey (AD-450): each file or `pubspec.yaml` key that can make a
//! `package:` URI name a file that the root `pubspec.yaml` alone does not give.
//!
//! The check reads lines, not YAML. It can find a key that YAML does not see, for example in a
//! block string; then the scope is UNKNOWN without need, never complete without proof.

use archkeel_pytext::splitlines;
use archkeel_snapshot::Snapshot;

use super::names::{GapName, Gaps, Place};
use crate::discover::{Discovery, PACKAGE_FILES};
use crate::pytext::{lstrip, strip};

const PUBSPEC: &str = "pubspec.yaml";

/// Add the package gaps of `discovery` and of the snapshot root to `gaps`.
pub(crate) fn package_gaps(snapshot: &mut Snapshot, discovery: &Discovery, gaps: &mut Gaps) {
    if discovery.pubspec_digest.is_some() {
        if let Some(raw) = snapshot.read(PUBSPEC) {
            pubspec_gaps(&raw, gaps);
        }
    }
    let mut files: Vec<String> = discovery.package_files.clone();
    for name in PACKAGE_FILES.iter().skip(1) {
        if snapshot.is_file(name) || snapshot.is_link(name) {
            files.push((*name).to_owned());
        }
    }
    files.sort();
    files.dedup();
    for rel in files.iter().filter(|rel| rel.as_str() != PUBSPEC) {
        if rel.rsplit('/').next() == Some(PUBSPEC) {
            let message = "a second package is inside a scan root; its URIs are not resolved";
            gaps.named(GapName::DartNestedPackage, Place::File(rel), message);
        } else {
            let message = "this file can map a package to another directory; it is not read";
            gaps.named(GapName::DartPackageConfig, Place::File(rel), message);
        }
    }
}

/// The gaps of the keys of the root `pubspec.yaml`. Bytes that are not UTF-8 already give the
/// SDK gap of the discovery.
fn pubspec_gaps(raw: &[u8], gaps: &mut Gaps) {
    let Ok(text) = std::str::from_utf8(raw) else {
        return;
    };
    let mut workspace = false;
    let mut path = false;
    for line in splitlines(text) {
        let body = strip(line.split('#').next().unwrap_or(""));
        if body.is_empty() {
            continue;
        }
        let top = lstrip(line).len() == line.len();
        workspace |= top && (key(body, "workspace") || key(body, "resolution"));
        // The whole line: a `#` inside a quoted flow value must not hide a later key.
        path |= has_path_key(strip(line));
    }
    if workspace {
        let message =
            "the package is a workspace or a member of one; its packages are not resolved";
        gaps.named(GapName::DartWorkspace, Place::File(PUBSPEC), message);
    }
    if path {
        let message = "a dependency has a local path; that package is outside the survey";
        gaps.named(GapName::DartPathDependency, Place::File(PUBSPEC), message);
    }
}

/// `body` is the key `name` with a value or a block: `name:` or `name: value`.
fn key(body: &str, name: &str) -> bool {
    body.strip_prefix(name)
        .map(lstrip)
        .is_some_and(|rest| rest.starts_with(':'))
}

/// `body` holds the key `path` in block form (`path: x`) or in flow form (`{path: x}`).
fn has_path_key(body: &str) -> bool {
    body.match_indices("path").any(|(at, _)| {
        let before = body.get(..at).and_then(|head| head.chars().next_back());
        let starts = before.is_none_or(|c| c.is_whitespace() || matches!(c, '{' | ',' | '-'));
        starts && key(body.get(at..).unwrap_or(""), "path")
    })
}

#[cfg(test)]
mod tests {
    use super::has_path_key;

    #[test]
    fn a_path_key_is_found_in_block_and_flow_form_only() {
        assert!(has_path_key("path: ../core"));
        assert!(has_path_key("core: {path: ../core}"));
        assert!(has_path_key("- path : x"));
        assert!(!has_path_key("classpath: x"));
        assert!(!has_path_key("description: a path to it"));
    }
}
