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
    /// The dependency names that a `[patch]` entry of the workspace sends to a path (`None`: to a git source).
    patches: BTreeMap<String, Option<String>>,
    /// `cargo metadata --no-deps` of the crate in a directory.
    describe: &'a dyn Fn(&Path) -> Option<Value>,
}

/// Where a dependency leads: a directory, or somewhere that cannot be told.
enum Target {
    Dir(String),
    /// A registry or git dependency that a `[patch]` entry sends to a directory: the scan reads no edge for it.
    Patched(String),
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
    let patches = patches(meta);
    let members = Members {
        dirs,
        names,
        patches,
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
        Target::Patched(dir) if members.dirs.contains_key(dir) => true,
        Target::Dir(dir) | Target::Patched(dir) => reaches_member(dir, members, known),
    }
}

fn real_dir(path: &str) -> Option<String> {
    let canonical = std::fs::canonicalize(path).ok()?;
    Some(canonical.to_string_lossy().replace('\\', "/"))
}

/// The `[patch]` entries of the workspace manifest: the dependency name (the `package` key when it renames) and the
/// directory that it is sent to. The text is read line by line: no TOML crate may read a manifest here, and an entry
/// that this reader does not understand (a git source, another form) leads to `None`, so it holds.
fn patches(meta: &Value) -> BTreeMap<String, Option<String>> {
    let root = meta.get("workspace_root").and_then(Value::as_str);
    let text = root.and_then(|r| std::fs::read_to_string(Path::new(r).join("Cargo.toml")).ok());
    let mut entries: Vec<Entry> = Vec::new();
    let (mut inside, mut table) = (false, false);
    for line in text.as_deref().unwrap_or_default().lines() {
        let line = line.split('#').next().unwrap_or_default().trim();
        if let Some(header) = line.strip_prefix('[') {
            let parts = key_parts(header.trim_end_matches(']'));
            inside = parts[0] == "patch";
            table = inside && parts.len() > 2;
            if table {
                entries.push(Entry::named(unquote(&parts[parts.len() - 1])));
            }
        } else if let (true, Some((key, value))) = (inside, line.split_once('=')) {
            match (table, entries.last_mut()) {
                (true, Some(last)) => last.set(key.trim(), value),
                (true, None) => {}
                (false, _) => entries.push(Entry::inline(unquote(key), value)),
            }
        }
    }
    let mut found: BTreeMap<String, Option<String>> = BTreeMap::new();
    for Entry { key, package, path } in entries {
        let dir = root
            .zip(path)
            .and_then(|(r, p)| real_dir(Path::new(r).join(p).to_str()?));
        // Two entries of one name: an entry that cannot be placed wins, so the name holds.
        let slot = found.entry(package.unwrap_or(key)).or_insert(dir.clone());
        if dir.is_none() {
            *slot = None;
        }
    }
    found
}

/// One entry of a `[patch]` table: its key, its `package` and its `path`.
struct Entry {
    key: String,
    package: Option<String>,
    path: Option<String>,
}

impl Entry {
    fn named(key: String) -> Entry {
        Entry {
            key,
            package: None,
            path: None,
        }
    }

    /// `name = { path = "..", package = ".." }`.
    fn inline(key: String, table: &str) -> Entry {
        Entry {
            key,
            package: inline_value(table, "package").map(str::to_owned),
            path: inline_value(table, "path").map(str::to_owned),
        }
    }

    /// A line of a `[patch.<source>.<name>]` table.
    fn set(&mut self, key: &str, value: &str) {
        let text = quoted(value).map(str::to_owned);
        match key {
            "path" => self.path = text,
            "package" => self.package = text,
            _ => {}
        }
    }
}

/// The string after the first quote of `value`.
fn quoted(value: &str) -> Option<&str> {
    let body = value.trim_start().strip_prefix('"')?;
    Some(&body[..body.find('"')?])
}

/// The string of `key = "..."` inside an inline table.
fn inline_value<'a>(table: &'a str, key: &str) -> Option<&'a str> {
    let at = word_at(table, key).next()?;
    quoted(table[at + key.len()..].trim_start().strip_prefix('=')?)
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

/// The parts of a dotted TOML key; a dot inside quotes is no separator.
fn key_parts(header: &str) -> Vec<String> {
    let (mut parts, mut current, mut quoted) = (Vec::new(), String::new(), false);
    for c in header.chars() {
        match c {
            '"' => {
                quoted = !quoted;
                current.push(c);
            }
            '.' if !quoted => parts.push(std::mem::take(&mut current)),
            _ => current.push(c),
        }
    }
    parts.push(current);
    parts
}

fn unquote(text: &str) -> String {
    text.trim().trim_matches('"').to_owned()
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
            found.push(patched.clone().map_or(Target::Unknown, Target::Patched));
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
                Target::Dir(d) | Target::Patched(d) if members.dirs.contains_key(d) => true,
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

/// Whether an `include!` or a `#[path]` in a Rust file below `dir` names a file outside the crate or inside a member,
/// or names a path that the search cannot tell (more files or bytes than the limits, a computed path). A file outside
/// the crate is not read here, so what it includes is unknown.
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
    let Some(own) = real_dir(dir.to_str().unwrap_or_default()) else {
        return true;
    };
    files.iter().any(|file| file_escapes(file, &own, members))
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
    // `#[path]` in a file that is no `mod.rs` is relative to the directory of the module.
    let bases = [
        Some(parent.to_path_buf()),
        file.file_stem().map(|s| parent.join(s)),
    ];
    let named = include_arguments(&text)
        .into_iter()
        .chain(path_attributes(&text));
    // `None`: the argument is no plain string literal, so the path cannot be told.
    named.into_iter().any(|literal| {
        let Some(literal) = literal else { return true };
        (bases.iter().flatten()).any(|base| escapes(base, literal, own, members))
    })
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
        let attribute = &rest[..rest.find(']').unwrap_or(rest.len())];
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

/// Whether `literal`, read from `base`, leaves the crate in `own`, lies inside a member, or cannot be resolved.
fn escapes(base: &Path, literal: &str, own: &str, members: &Members) -> bool {
    let Some(target) = real_dir(base.join(literal).to_str().unwrap_or_default()) else {
        return true;
    };
    let inside = |dir: &str| target == dir || target.starts_with(&format!("{dir}/"));
    !inside(own) || members.dirs.keys().any(|member| inside(member))
}
