// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package gaps of the survey (AD-454): each file or `pubspec.yaml` key that can make a
//! `package:` URI name a file that the root `pubspec.yaml` alone does not give.
//!
//! The workspace has no YAML parser, so the check reads words, not YAML (AD-496). A YAML key is a
//! scalar. Without a backslash escape, the text of a scalar is in the file as it is: a quoted key,
//! a flow key and an explicit `?` key alike, and a folded line break gives a space, never a join.
//! So each word `path`, `workspace` or `resolution` outside a comment line is a gap, and each
//! backslash is a gap, because an escape can spell a key that the file does not hold as text. A
//! word in a value or a block string gives a gap without need, never a complete scope without proof.

use archkeel_snapshot::Snapshot;

use super::names::{GapName, Gaps, Place};
use crate::discover::{Discovery, PACKAGE_FILES};

const PUBSPEC: &str = "pubspec.yaml";

/// Add the package gaps of `discovery`, of the snapshot root and of each directory above a scan
/// root to `gaps`. A package file above a scan root can own the files below it, as the root
/// `pubspec.yaml` owns `lib`.
pub(crate) fn package_gaps(
    snapshot: &mut Snapshot,
    discovery: &Discovery,
    roots: &[String],
    gaps: &mut Gaps,
) {
    if discovery.pubspec_digest.is_some() {
        if let Some(raw) = snapshot.read(PUBSPEC) {
            pubspec_gaps(&raw, gaps);
        }
    }
    let mut files: Vec<String> = discovery.package_files.clone();
    let above = roots.iter().flat_map(|root| {
        let parts: Vec<&str> = root.split('/').collect();
        (1..parts.len()).map(move |end| parts[..end].join("/"))
    });
    let dirs: Vec<String> = std::iter::once(String::new()).chain(above).collect();
    for dir in dirs
        .iter()
        .filter(|dir| !matches!(dir.as_str(), "." | ".."))
    {
        for name in PACKAGE_FILES {
            let rel = if dir.is_empty() {
                name.to_owned()
            } else {
                format!("{dir}/{name}")
            };
            if snapshot.is_file(&rel) || snapshot.is_link(&rel) {
                files.push(rel);
            }
        }
    }
    files.sort();
    files.dedup();
    for rel in files.iter().filter(|rel| rel.as_str() != PUBSPEC) {
        if rel.rsplit('/').next() == Some(PUBSPEC) {
            let message = "a second package holds or is in a scan root; its URIs are not resolved";
            gaps.named(GapName::DartNestedPackage, Place::File(rel), message);
        } else {
            let message = "this file can map a package to another directory; it is not read";
            gaps.named(GapName::DartPackageConfig, Place::File(rel), message);
        }
    }
}

/// The key words that the root `pubspec.yaml` holds outside a comment line.
#[derive(Debug, Default, PartialEq, Eq)]
struct PubspecWords {
    workspace: bool,
    path: bool,
    escape: bool,
}

/// Read the words of `text`. A YAML line break is `\n` or `\r`; a comment line has only spaces or
/// tabs before its `#`, and no part of such a line can be a key of a YAML scalar alone.
fn keys(text: &str) -> PubspecWords {
    let mut found = PubspecWords {
        escape: text.contains('\\'),
        ..PubspecWords::default()
    };
    for line in text.split(['\n', '\r']) {
        if line.trim_start_matches([' ', '\t']).starts_with('#') {
            continue;
        }
        for word in line.split(|c: char| !c.is_ascii_alphanumeric()) {
            match word {
                "path" => found.path = true,
                "workspace" | "resolution" => found.workspace = true,
                _ => {}
            }
        }
    }
    found
}

/// The gaps of the keys of the root `pubspec.yaml`. Bytes that are not UTF-8 already give the
/// SDK gap of the discovery.
fn pubspec_gaps(raw: &[u8], gaps: &mut Gaps) {
    let Ok(text) = std::str::from_utf8(raw) else {
        return;
    };
    let found = keys(text);
    if found.workspace {
        let message =
            "the package is a workspace or a member of one; its packages are not resolved";
        gaps.named(GapName::DartWorkspace, Place::File(PUBSPEC), message);
    }
    if found.path {
        let message = "a dependency has a local path; that package is outside the survey";
        gaps.named(GapName::DartPathDependency, Place::File(PUBSPEC), message);
    }
    if found.escape && !found.path {
        let message = "an escape can spell a local path key; the pubspec is not read";
        gaps.named(GapName::DartPathDependency, Place::File(PUBSPEC), message);
    }
}

#[cfg(test)]
mod tests {
    use super::keys;

    fn words(text: &str) -> (bool, bool, bool) {
        let found = keys(text);
        (found.workspace, found.path, found.escape)
    }

    #[test]
    fn each_yaml_form_of_a_key_is_a_word_and_an_escape_is_a_gap() {
        for text in [
            "a:\n  b:\n    path: x",
            "a: {\"b\": {\"path\": x}}",
            "a:\n  'path': x",
            "a:\n  ? path\n  : x",
            "a:\n  ? \"path\"\n  : x",
            "a: {b: {path : x}}",
        ] {
            assert_eq!(words(text), (false, true, false), "{text}");
        }
        assert_eq!(words("\"workspace\":\n  - x"), (true, false, false));
        assert_eq!(words("'resolution': workspace"), (true, false, false));
        // The key alone is a gap: the value need not be the word `workspace`.
        assert_eq!(words("\"resolution\": x"), (true, false, false));
        assert_eq!(words("a:\n  \"pa\\x74h\": x"), (false, false, true));
    }

    #[test]
    fn a_comment_line_and_a_longer_word_are_no_key() {
        assert_eq!(words("  # path: x\nclasspath: x"), (false, false, false));
        assert_eq!(words("description: a pathway"), (false, false, false));
        // A trailing comment is read: a gap without need, never a hidden key.
        assert_eq!(words("name: x # path"), (false, true, false));
    }
}
