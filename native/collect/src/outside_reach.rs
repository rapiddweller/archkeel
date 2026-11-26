// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The members that reach another member through code that the scan does not read (#2028, #2060, AD-1097).
//!
//! The scan reads the workspace members only. A member can still run a crate that lies elsewhere, and that crate can
//! run a member: through a path dependency, a registry or git dependency that a `[patch]` entry sends to a path, a git
//! dependency on a member, or an `include!` or `#[path]` that names a file of a member. The edges of such a member are
//! unknown, so the worker holds them with a gap.

use crate::rustc_facts_members::metadata;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

/// The member directories (canonical) and the member package names.
struct Members<'a> {
    dirs: &'a BTreeMap<String, BTreeSet<String>>,
    names: &'a BTreeSet<String>,
    /// The dependency names that a `[patch]` entry of the workspace sends to a path (`None`: to a git source).
    patches: BTreeMap<String, Option<String>>,
}

/// Where a dependency leads: a directory, or somewhere that cannot be told.
enum Target {
    Dir(String),
    Unknown,
}

/// The canonical directory of each member that has a dependency on a crate that is no member and that reaches a member.
/// A crate that Cargo cannot describe counts as reaching one.
pub(crate) fn dependents(
    meta: &Value,
    ids: &BTreeSet<&str>,
    dirs: &BTreeMap<String, BTreeSet<String>>,
    names: &BTreeSet<String>,
) -> BTreeSet<String> {
    let patches = patches(meta);
    let members = Members {
        dirs,
        names,
        patches,
    };
    let mut known = BTreeMap::new();
    let mut found = BTreeSet::new();
    let packages = meta.get("packages").and_then(Value::as_array);
    for package in packages.into_iter().flatten() {
        let id = package.get("id").and_then(Value::as_str);
        let manifest = package.get("manifest_path").and_then(Value::as_str);
        let dir = manifest.and_then(|m| real_dir(Path::new(m).parent()?.to_str()?));
        let (true, Some(dir)) = (ids.contains(id.unwrap_or_default()), dir) else {
            continue;
        };
        if targets(package, &members)
            .iter()
            .any(|target| held(target, &members, &mut known))
        {
            found.insert(dir);
        }
    }
    found
}

fn held(target: &Target, members: &Members, known: &mut BTreeMap<String, bool>) -> bool {
    match target {
        Target::Unknown => true,
        Target::Dir(dir) if members.dirs.contains_key(dir) => false,
        Target::Dir(dir) => reaches_member(dir, members, known),
    }
}

fn real_dir(path: &str) -> Option<String> {
    let canonical = std::fs::canonicalize(path).ok()?;
    Some(canonical.to_string_lossy().replace('\\', "/"))
}

/// The `[patch]` entries of the workspace manifest: the dependency name and the directory that it is sent to.
fn patches(meta: &Value) -> BTreeMap<String, Option<String>> {
    let root = meta.get("workspace_root").and_then(Value::as_str);
    let text = root.and_then(|r| std::fs::read_to_string(Path::new(r).join("Cargo.toml")).ok());
    let table = text.and_then(|t| t.parse::<toml::Table>().ok());
    let mut found = BTreeMap::new();
    let sources = table.as_ref().and_then(|t| t.get("patch")?.as_table());
    for entries in sources.into_iter().flat_map(|s| s.values()) {
        for (name, entry) in entries.as_table().into_iter().flatten() {
            let path = entry.get("path").and_then(toml::Value::as_str);
            let dir = path
                .zip(root)
                .and_then(|(p, r)| real_dir(Path::new(r).join(p).to_str()?));
            found.insert(name.clone(), dir);
        }
    }
    found
}

/// What each dependency of `package` leads to. A registry or git entry has no path in the metadata: a `[patch]`
/// entry gives one, and a git entry that names a member can lead into the repository.
fn targets(package: &Value, members: &Members) -> Vec<Target> {
    let dependencies = package.get("dependencies").and_then(Value::as_array);
    let mut found = Vec::new();
    for dependency in dependencies.into_iter().flatten() {
        let name = dependency.get("name").and_then(Value::as_str);
        let source = dependency.get("source").and_then(Value::as_str);
        if let Some(path) = dependency.get("path").and_then(Value::as_str) {
            found.push(real_dir(path).map_or(Target::Unknown, Target::Dir));
        } else if let Some(patched) = name.and_then(|n| members.patches.get(n)) {
            found.push(patched.clone().map_or(Target::Unknown, Target::Dir));
        } else if source.is_some_and(|s| s.starts_with("git+"))
            && name.is_some_and(|n| members.names.contains(n))
        {
            found.push(Target::Unknown);
        }
    }
    found
}

/// Whether the crate in `dir` (no member) reaches a member. `known` holds the answers; a crate on the way counts as
/// `false` until it is decided, so a cycle ends.
fn reaches_member(dir: &str, members: &Members, known: &mut BTreeMap<String, bool>) -> bool {
    if let Some(&answer) = known.get(dir) {
        return answer;
    }
    known.insert(dir.to_owned(), false);
    let described = metadata(&Path::new(dir).join("Cargo.toml"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok());
    let reaches = match described {
        None => true,
        Some(meta) => {
            let packages = meta.get("packages").and_then(Value::as_array);
            let targets: Vec<Target> = packages
                .into_iter()
                .flatten()
                .flat_map(|p| targets(p, members))
                .collect();
            // A dependency of a crate outside the scan that leads to a member is the route back.
            let by_dependency = targets.iter().any(|t| match t {
                Target::Dir(d) if d == dir => false,
                Target::Dir(d) if members.dirs.contains_key(d) => true,
                other => held(other, members, known),
            });
            by_dependency || sources_reach_member(Path::new(dir), members)
        }
    };
    known.insert(dir.to_owned(), reaches);
    reaches
}

/// The most files and bytes that the text search of one crate reads.
const MAX_FILES: usize = 5000;
const MAX_BYTES: u64 = 4 << 20;

/// Whether an `include!` or a `#[path]` in a Rust file below `dir` names a file of a member, or names a path that the
/// search cannot tell (more files or bytes than the limits, a computed path).
fn sources_reach_member(dir: &Path, members: &Members) -> bool {
    let mut files = Vec::new();
    let mut pending = vec![dir.to_path_buf()];
    while let Some(next) = pending.pop() {
        let Ok(entries) = std::fs::read_dir(&next) else {
            return true;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let skip = matches!(entry.file_name().to_str(), Some("target" | ".git"));
            if path.is_dir() && !skip {
                pending.push(path);
            } else if path.extension().is_some_and(|e| e == "rs") {
                files.push(path);
            }
        }
        if files.len() > MAX_FILES {
            return true;
        }
    }
    files.iter().any(|file| file_reaches_member(file, members))
}

fn file_reaches_member(file: &Path, members: &Members) -> bool {
    let large = std::fs::metadata(file).is_ok_and(|m| m.len() > MAX_BYTES);
    let Ok(text) = std::fs::read_to_string(file) else {
        return true;
    };
    if large {
        return true;
    }
    let parent = file.parent().unwrap_or(Path::new("."));
    // `#[path]` in a file that is no `mod.rs` is relative to the directory of the module.
    let own = file.file_stem().map(|stem| parent.join(stem));
    for pattern in ["include!", "#[path"] {
        for (at, _) in text.match_indices(pattern) {
            let Some(literal) = first_literal(&text[at + pattern.len()..]) else {
                return true;
            };
            let bases = [Some(parent.to_path_buf()), own.clone()];
            if (bases.iter().flatten()).any(|base| names_member(base, literal, members)) {
                return true;
            }
        }
    }
    false
}

/// The first string literal within 200 characters of the start of `rest`.
fn first_literal(rest: &str) -> Option<&str> {
    let start = rest.char_indices().take(200).find(|(_, c)| *c == '"')?.0;
    let body = &rest[start + 1..];
    Some(&body[..body.find('"')?])
}

/// Whether `literal`, read from `base`, is a path inside a member.
fn names_member(base: &Path, literal: &str, members: &Members) -> bool {
    let target = real_dir(base.join(literal).to_str().unwrap_or_default());
    let inside = |t: &String, m: &String| t == m || t.starts_with(&format!("{m}/"));
    target.is_some_and(|t| members.dirs.keys().any(|m| inside(&t, m)))
}
