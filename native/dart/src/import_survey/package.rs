// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package gaps of the survey (AD-454): each file or `pubspec.yaml` key that can make a
//! `package:` URI name a file that the root `pubspec.yaml` alone does not give.
//!
//! A bounded YAML parse finds keys, not words in scalar values. An unreadable form keeps a gap.

use archkeel_facts::envelope::{Input, Role};
use archkeel_facts::identity::sha256_hex;
use archkeel_snapshot::Snapshot;
use saphyr::{LoadableYamlNode, Yaml};

use super::index::Index;
use super::names::{GapName, Gaps, Place};
use crate::discover::{Discovery, PACKAGE_FILES};
use crate::module::is_identifier;

const PUBSPEC: &str = "pubspec.yaml";

/// Add the package gaps of `discovery`, of the snapshot root and of each directory above a scan
/// root to `gaps`. A package file above a scan root can own the files below it, as the root
/// `pubspec.yaml` owns `lib`.
pub(crate) fn package_gaps(
    snapshot: &mut Snapshot,
    discovery: &Discovery,
    roots: &[String],
    index: &Index<'_>,
    gaps: &mut Gaps,
) -> Vec<Input> {
    let mut inputs = Vec::new();
    if discovery.pubspec_digest.is_some() {
        if let Some(raw) = snapshot.read(PUBSPEC) {
            pubspec_gaps(&raw, snapshot, discovery, roots, index, gaps, &mut inputs);
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
    inputs
}

/// The package keys and the marker for an unreadable document.
#[derive(Debug, Default, PartialEq, Eq)]
struct PubspecWords {
    workspace: bool,
    resolution: bool,
    path: bool,
    escape: bool,
}

/// Parse one bounded YAML document. Other documents retain a conservative gap.
fn yaml(text: &str) -> Option<Yaml<'_>> {
    if !text.contains('\\')
        && text.len() <= 65_536
        && text
            .lines()
            .all(|line| line.len() - line.trim_start().len() <= 128)
        && text
            .bytes()
            .filter(|byte| matches!(byte, b'[' | b'{' | b'-' | b':' | b'?'))
            .count()
            <= 128
    {
        if let Ok(mut documents) = Yaml::load_from_str(text) {
            if documents.len() == 1 {
                return documents.pop();
            }
        }
    }
    None
}

fn keys(text: &str) -> PubspecWords {
    if let Some(document) = yaml(text) {
        let mut found = PubspecWords::default();
        if yaml_keys(&document, &mut found, 0) {
            return found;
        }
    }
    let mut found = words(text);
    found.escape = true;
    found
}

fn yaml_keys(node: &Yaml<'_>, found: &mut PubspecWords, depth: usize) -> bool {
    if depth > 128 {
        return false;
    }
    match node {
        Yaml::Mapping(map) => map.iter().all(|(key, value)| {
            let Some(key) = key.as_str() else {
                return false;
            };
            match key {
                "path" => found.path = true,
                "workspace" => found.workspace = true,
                "resolution" => {
                    found.workspace = true;
                    found.resolution = true;
                }
                "<<" => return false,
                _ => {}
            }
            yaml_keys(value, found, depth + 1)
        }),
        Yaml::Sequence(items) => items.iter().all(|item| yaml_keys(item, found, depth + 1)),
        Yaml::Value(_) => true,
        _ => false,
    }
}

fn words(text: &str) -> PubspecWords {
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
                "workspace" => found.workspace = true,
                "resolution" => {
                    found.workspace = true;
                    found.resolution = true;
                }
                _ => {}
            }
        }
    }
    found
}

fn workspace(
    text: &str,
    snapshot: &mut Snapshot,
    own: &str,
    roots: &[String],
    index: &Index<'_>,
    inputs: &mut Vec<Input>,
) -> bool {
    if text.contains(['&', '*', '!', '\\']) || index.syntax.iter().any(Option::is_none) {
        return false;
    }
    if snapshot.is_file("pubspec.lock") || snapshot.is_link("pubspec.lock") {
        return false;
    }
    let Some(document) = yaml(text) else {
        return false;
    };
    if document.as_mapping_get("dependency_overrides").is_some() {
        return false;
    }
    let Some(members) = document
        .as_mapping_get("workspace")
        .and_then(Yaml::as_sequence)
    else {
        return false;
    };
    if members.len() > 32 || own.is_empty() {
        return false;
    }
    let mut names = std::collections::BTreeSet::from([own.to_owned()]);
    let mut read = Vec::new();
    for member in members {
        let Some(dir) = member.as_str().filter(|s| is_identifier(s)) else {
            return false;
        };
        if roots
            .iter()
            .any(|root| root == "." || root.split('/').next() == Some(dir))
            || snapshot.is_link(dir)
            || snapshot.is_file(&format!("{dir}/pubspec_overrides.yaml"))
            || snapshot.is_link(&format!("{dir}/pubspec_overrides.yaml"))
        {
            return false;
        }
        let path = format!("{dir}/pubspec.yaml");
        if snapshot.is_link(&path) {
            return false;
        }
        let Some(raw) = snapshot.read(&path) else {
            return false;
        };
        let Ok(member_text) = std::str::from_utf8(&raw) else {
            return false;
        };
        if member_text.contains(['&', '*', '!', '\\']) {
            return false;
        }
        let Some(doc) = yaml(member_text) else {
            return false;
        };
        let Some(name) = doc
            .as_mapping_get("name")
            .and_then(Yaml::as_str)
            .filter(|s| is_identifier(s))
        else {
            return false;
        };
        if !names.insert(name.to_owned()) || !member_safe(&doc) || member_imported(index, name) {
            return false;
        }
        read.push(Input {
            digest: sha256_hex(&raw),
            path,
            role: Role::Resolution,
        });
    }
    inputs.extend(read);
    true
}

fn member_safe(doc: &Yaml<'_>) -> bool {
    let Some(map) = doc.as_mapping() else {
        return false;
    };
    for (key, value) in map {
        let Some(key) = key.as_str() else {
            return false;
        };
        if matches!(key, "workspace" | "dependency_overrides") {
            return false;
        }
        if key == "resolution" {
            if value.as_str() != Some("workspace") {
                return false;
            }
            continue;
        }
        let mut found = PubspecWords::default();
        if matches!(key, "dependencies" | "dev_dependencies") {
            let Some(deps) = value.as_mapping() else {
                return false;
            };
            if !deps
                .iter()
                .all(|(name, value)| name.as_str().is_some() && yaml_keys(value, &mut found, 0))
            {
                return false;
            }
        } else if !yaml_keys(value, &mut found, 0) {
            return false;
        }
        if found.path || found.workspace {
            return false;
        }
    }
    true
}

fn member_imported(index: &Index<'_>, name: &str) -> bool {
    index.syntax.iter().flatten().any(|syntax| syntax.directives.iter().any(|directive| {
        directive.target.as_deref().into_iter()
            .chain(directive.alternatives.iter().map(|(_, uri)| uri.as_str()))
            .any(|uri| matches!(super::uri::classify("", uri, index.package), super::uri::Uri::External { package, .. } if package == name))
    }))
}

/// The gaps of the keys of the root `pubspec.yaml`. Bytes that are not UTF-8 already give the
/// SDK gap of the discovery.
fn pubspec_gaps(
    raw: &[u8],
    snapshot: &mut Snapshot,
    discovery: &Discovery,
    roots: &[String],
    index: &Index<'_>,
    gaps: &mut Gaps,
    inputs: &mut Vec<Input>,
) {
    let Ok(text) = std::str::from_utf8(raw) else {
        return;
    };
    let found = keys(text);
    if found.workspace
        && (found.resolution
            || found.path
            || found.escape
            || !workspace(
                text,
                snapshot,
                &discovery.package_name,
                roots,
                index,
                inputs,
            ))
    {
        let message =
            "the package is a workspace or a member of one; its packages are not resolved";
        gaps.named(GapName::DartWorkspace, Place::File(PUBSPEC), message);
    }
    if found.path {
        let message = "a dependency has a local path; that package is outside the survey";
        gaps.named(GapName::DartPathDependency, Place::File(PUBSPEC), message);
    }
    if found.escape && !found.path {
        let message = "the pubspec is not fully read; it can hide a local path key";
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
        assert_eq!(words("name: x # path"), (false, false, false));
    }

    #[test]
    fn path_in_package_metadata_is_not_a_dependency_key() {
        assert_eq!(
            words(
                "name: path\ndescription: A path library\nrepository: https://example.org/path\n"
            ),
            (false, false, false)
        );
    }

    #[test]
    fn path_keys_and_unreadable_yaml_keep_a_gap() {
        for text in [
            "dependencies:\n  other:\n    path: ../other\n",
            "dependency_overrides: {other: {path: ../other}}",
            "dependencies:\n  other:\n    'path': ../other",
            "dependencies:\n  other:\n    \"pa\\x74h\": ../other",
            "name: path\nname: other\n",
            "name: path\nx: [\n",
            "name: path\nx: &a {path: ../other}\ny: *a\n",
        ] {
            let found = keys(text);
            assert!(found.path || found.escape, "{text:?}: {found:?}");
        }
    }
}
