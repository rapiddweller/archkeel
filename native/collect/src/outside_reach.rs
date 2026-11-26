// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The members that reach another member through code that the scan does not read (#2028, #2060, AD-1097).
//!
//! The scan reads the workspace members only. A member can still run a crate that lies elsewhere, and that crate can
//! run a member: through a path dependency, a registry or git dependency that a `[patch]` entry sends to a path, a git
//! dependency on a member, or an `include!` or `#[path]` that names a file of a member. The edges of such a member are
//! unknown, so the worker holds them with a gap.

use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

/// The member directories (canonical) and the member package names.
struct Members<'a> {
    dirs: &'a BTreeMap<String, BTreeSet<String>>,
    names: &'a BTreeSet<String>,
    /// The workspace manifest, when a `[patch]` or `[replace]` can send a registry or git dependency elsewhere.
    patched: Option<String>,
    /// `cargo metadata --no-deps` of the crate in a directory.
    describe: &'a dyn Fn(&Path) -> Option<Value>,
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
    describe: &dyn Fn(&Path) -> Option<Value>,
) -> BTreeSet<String> {
    let patched = patch_text(meta);
    let members = Members {
        dirs,
        names,
        patched,
        describe,
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

/// The text of the workspace manifest when it has a `[patch]` or `[replace]` entry. The text is not parsed: a name that
/// occurs anywhere in it can be patched, whatever the syntax (an alias, a literal string, a dotted key).
fn patch_text(meta: &Value) -> Option<String> {
    let root = meta.get("workspace_root").and_then(Value::as_str)?;
    let text = std::fs::read_to_string(Path::new(root).join("Cargo.toml")).ok()?;
    (text.contains("patch") || text.contains("replace")).then_some(text)
}

/// The start of each whole-word occurrence of `word` in `text`.
fn word_at<'a>(text: &'a str, word: &'a str) -> impl Iterator<Item = usize> + 'a {
    let ident = |c: char| c.is_alphanumeric() || c == '_';
    text.match_indices(word)
        .map(|(at, _)| at)
        .filter(move |&at| {
            let before = text[..at].chars().next_back();
            let after = text[at + word.len()..].chars().next();
            !before.is_some_and(ident) && !after.is_some_and(ident)
        })
}

/// A registry or git dependency whose name occurs in the workspace manifest that has a `[patch]` or `[replace]`.
fn patchable(source: Option<&str>, name: Option<&str>, members: &Members) -> bool {
    let text = members.patched.as_ref();
    source.is_some() && name.is_some_and(|n| text.is_some_and(|t| t.contains(n)))
}

/// A git dependency that names a member can lead into the repository.
fn git_member(source: Option<&str>, name: Option<&str>, members: &Members) -> bool {
    let git = source.is_some_and(|s| s.starts_with("git+"));
    git && name.is_some_and(|n| members.names.contains(n))
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
        } else if patchable(source, name, members) || git_member(source, name, members) {
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
    let described = (members.describe)(&Path::new(dir).join("Cargo.toml"));
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
            by_dependency || sources_reach_member(Path::new(dir), members, &meta)
        }
    };
    known.insert(dir.to_owned(), reaches);
    reaches
}

/// The most files and bytes that the text search of one crate reads.
const MAX_FILES: usize = 5000;
const MAX_BYTES: u64 = 4 << 20;

/// Whether an `include!` or a `#[path]` in a Rust file below `dir` names a file outside the crate or inside a member,
/// or names a path that the search cannot tell (more files or bytes than the limits, a computed path). A file outside
/// the crate is not read here, so what it includes is unknown.
fn sources_reach_member(dir: &Path, members: &Members, meta: &Value) -> bool {
    // Cargo compiles each target `src_path` as Rust, whatever its extension.
    let Some(own) = real_dir(dir.to_str().unwrap_or_default()) else {
        return true;
    };
    let mut files = target_sources(meta);
    // A target source inside a member, or outside the crate, is the route itself: the search does not read it as the crate.
    if files.iter().any(|f| {
        !real_dir(f.to_str().unwrap_or_default()).is_some_and(|t| crate_owns(&t, &own, members))
    }) {
        return true;
    }
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
    files.iter().any(|file| file_escapes(file, &own, members))
}

fn target_sources(meta: &Value) -> Vec<std::path::PathBuf> {
    let packages = meta.get("packages").and_then(Value::as_array);
    let targets = packages
        .into_iter()
        .flatten()
        .filter_map(|p| p.get("targets")?.as_array());
    let paths = targets
        .flatten()
        .filter_map(|t| t.get("src_path")?.as_str());
    paths.map(std::path::PathBuf::from).collect()
}

fn file_escapes(file: &Path, own: &str, members: &Members) -> bool {
    let large = std::fs::metadata(file).is_ok_and(|m| m.len() > MAX_BYTES);
    let Ok(text) = std::fs::read_to_string(file) else {
        return true;
    };
    if large {
        return true;
    }
    let parent = file.parent().unwrap_or(Path::new("."));
    // `include!` is relative to the file. `#[path]` is relative to the directory of the file in a `mod.rs`, `lib.rs`
    // or `main.rs`, and to the directory of the module otherwise: an unresolved candidate is no proof of a route.
    let stem = file.file_stem().map(|s| parent.join(s));
    let attributes = path_attributes(&text);
    let attribute_bases = [Some(parent.to_path_buf()), stem];
    let includes = include_arguments(&text);
    let leaves = |literal: Option<&str>, bases: &[Option<std::path::PathBuf>]| {
        let Some(literal) = literal else { return true };
        let reads: Vec<Option<bool>> = (bases.iter().flatten())
            .map(|base| escapes(base, literal, own, members))
            .collect();
        reads.contains(&Some(true)) || reads.iter().all(Option::is_none)
    };
    let include_base = [Some(parent.to_path_buf())];
    includes.into_iter().any(|l| leaves(l, &include_base))
        || attributes.into_iter().any(|l| leaves(l, &attribute_bases))
}

/// The argument of each `include!` call: `Some(literal)` when it is a plain string literal.
fn include_arguments(text: &str) -> Vec<Option<&str>> {
    let mut found = Vec::new();
    for at in word_at(text, "include") {
        let Some(rest) = trivia(&text[at + "include".len()..]).strip_prefix('!') else {
            continue;
        };
        let rest = trivia(rest);
        let opened = rest.strip_prefix(['(', '[', '{']).map(trivia);
        found.push(opened.and_then(whole_literal));
    }
    found
}

/// The literal of each `path = ".."` inside an attribute (`#[path = ".."]`, `#[cfg_attr(.., path = "..")]`).
fn path_attributes(text: &str) -> Vec<Option<&str>> {
    let mut found = Vec::new();
    for (at, _) in text.match_indices('#') {
        let rest = trivia(&text[at + 1..]);
        let Some(rest) = trivia(rest.strip_prefix('!').unwrap_or(rest)).strip_prefix('[') else {
            continue;
        };
        let attribute = &rest[..rest.find(']').map_or(rest.len(), |end| end + 1)];
        for key in word_at(attribute, "path") {
            let value = trivia(&attribute[key + "path".len()..]).strip_prefix('=');
            found.push(value.map(trivia).and_then(whole_literal));
        }
    }
    found
}

/// Skip white space and comments.
fn trivia(mut text: &str) -> &str {
    loop {
        text = text.trim_start();
        if let Some(line) = text.strip_prefix("//") {
            text = line.split_once('\n').map_or("", |(_, rest)| rest);
        } else if let Some(block) = text.strip_prefix("/*") {
            text = block.split_once("*/").map_or("", |(_, rest)| rest);
        } else {
            return text;
        }
    }
}

/// A string literal that is the whole argument: it is followed by a closer, not by more of an expression.
fn whole_literal(rest: &str) -> Option<&str> {
    let body = rest.strip_prefix('"')?;
    let literal = &body[..body.find('"')?];
    let after = trivia(&body[literal.len() + 1..]);
    after.starts_with([')', ']', ';', '}']).then_some(literal)
}

/// Whether the canonical path `target` lies in the crate `own` and in no member.
fn crate_owns(target: &str, own: &str, members: &Members) -> bool {
    let inside = |dir: &str| target == dir || target.starts_with(&format!("{dir}/"));
    inside(own) && !members.dirs.keys().any(|member| inside(member))
}

/// Whether `literal`, read from `base`, leaves the crate in `own`, lies inside a member, or names a file that the
/// search does not read (no `.rs` file, or a file below `target` or `.git`); `None` when it does not resolve.
fn escapes(base: &Path, literal: &str, own: &str, members: &Members) -> Option<bool> {
    let target = real_dir(base.join(literal).to_str()?)?;
    let inside = |dir: &str| target == dir || target.starts_with(&format!("{dir}/"));
    let below = target.strip_prefix(own).unwrap_or_default();
    let unread = !target.ends_with(".rs")
        || below
            .split('/')
            .any(|part| part == "target" || part == ".git");
    Some(!inside(own) || members.dirs.keys().any(|member| inside(member)) || unread)
}
