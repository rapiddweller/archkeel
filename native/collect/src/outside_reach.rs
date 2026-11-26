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
    // A backslash can write the table name in an escape (`pa\u0074ch`), so such a manifest is kept too.
    (text.contains("patch") || text.contains("replace") || text.contains('\\')).then_some(text)
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
    // A backslash can write a name in an escape (`\u002d`): the text cannot rule a patch out.
    let named = |t: &String| t.contains('\\') || name.is_some_and(|n| t.contains(n));
    source.is_some() && text.is_some_and(named)
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
    let mut pending = vec![dir.to_path_buf()];
    // A directory symlink can lead back: each real directory is read once.
    let mut seen = std::collections::BTreeSet::new();
    while let Some(next) = pending.pop() {
        if !real_dir(next.to_str().unwrap_or_default()).is_some_and(|real| seen.insert(real)) {
            continue;
        }
        let Ok(entries) = std::fs::read_dir(&next) else {
            return true;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            // Only the build output and the repository of the crate itself: a module can have either name (`escapes` agrees).
            let skip = path == dir.join("target") || path == dir.join(".git");
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
    // Each source, whether a target or found by the walk, must lie in the crate and in no member after its symlinks are
    // resolved: a source that does not is the route itself.
    let owned = |file: &std::path::PathBuf| {
        real_dir(file.to_str().unwrap_or_default()).is_some_and(|t| crate_owns(&t, &own, members))
    };
    !files.iter().all(owned) || files.iter().any(|file| file_escapes(file, &own, members))
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
    // The size is read first: the limit must bound the memory.
    if std::fs::metadata(file).is_ok_and(|m| m.len() > MAX_BYTES) {
        return true;
    }
    let Ok(text) = std::fs::read_to_string(file) else {
        return true;
    };
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

/// Each whole-word `word` in `text` with the text after it when `mark` follows (white space and comments between).
fn marked<'a>(
    text: &'a str,
    word: &'a str,
    mark: char,
) -> impl Iterator<Item = (usize, Option<&'a str>)> + 'a {
    word_at(text, word).map(move |at| (at, trivia(&text[at + word.len()..]).strip_prefix(mark)))
}

/// The argument of each `include!` call: `Some(literal)` when it is a plain string literal.
fn include_arguments(text: &str) -> Vec<Option<&str>> {
    let mut found = Vec::new();
    for (at, call) in marked(text, "include", '!') {
        let Some(rest) = call else {
            // `use std::include as load;` or a path to the macro: the call is not followed here, so it holds. A line
            // that starts with `//` is a comment, whatever it holds.
            let line = text[..at].rsplit('\n').next().unwrap_or_default();
            if !line.trim_start().starts_with("//") {
                found.push(None);
            }
            continue;
        };
        let opened = trivia(rest).strip_prefix(['(', '[', '{']).map(trivia);
        // A call whose argument is no plain literal cannot be told: it holds.
        found.push(opened.and_then(literal_argument).unwrap_or(None));
    }
    found
}

/// The literal of each `path = ".."` in the text, wherever it stands: an attribute can end in a place that a search
/// without a lexer cannot tell (`cfg_attr(.., doc = "]", path = ".."`). A `path =` that is followed by `$` (a macro
/// argument) cannot be told and gives `None`; a `path =` that is followed by another expression is no attribute.
fn path_attributes(text: &str) -> Vec<Option<&str>> {
    // A value that is no string literal at all is no attribute; one that cannot be read holds.
    let values = marked(text, "path", '=').filter_map(|(_, value)| value);
    values
        .filter_map(|value| literal_argument(trivia(value)))
        .collect()
}

/// The reading of a value: `Some(Some(literal))` for a plain string literal, `Some(None)` for a value that looks like a
/// string but cannot be read here (a raw, byte or C string, a macro argument), `None` for anything else.
fn literal_argument(value: &str) -> Option<Option<&str>> {
    if value.starts_with('"') {
        return Some(whole_literal(value));
    }
    let prefixed = value.starts_with(['r', 'b', 'c']) && value[1..].starts_with(['"', '#', 'r']);
    (prefixed || value.starts_with('$')).then_some(None)
}

/// Skip white space and comments.
fn trivia(mut text: &str) -> &str {
    loop {
        text = text.trim_start();
        if let Some(line) = text.strip_prefix("//") {
            text = line.split_once('\n').map_or("", |(_, rest)| rest);
        } else if let Some(block) = text.strip_prefix("/*") {
            text = after_block(block);
        } else {
            return text;
        }
    }
}

/// The text after the end of a block comment whose opener is already read; block comments nest in Rust.
fn after_block(text: &str) -> &str {
    let (mut depth, mut at) = (1, 0);
    while depth > 0 {
        let rest = &text[at..];
        let (open, close) = (rest.find("/*"), rest.find("*/"));
        match (open, close) {
            (_, None) => return "",
            (Some(o), Some(c)) if o < c => {
                depth += 1;
                at += o + 2;
            }
            (_, Some(c)) => {
                depth -= 1;
                at += c + 2;
            }
        }
    }
    &text[at..]
}

/// A string literal that is the whole argument: it is followed by a closer, not by more of an expression.
fn whole_literal(rest: &str) -> Option<&str> {
    let body = rest.strip_prefix('"')?;
    let literal = &body[..body.find('"')?];
    let after = trivia(&body[literal.len() + 1..]);
    after
        .starts_with([')', ']', ';', '}', ','])
        .then_some(literal)
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
    // The first part below the crate: the build output and the repository are not searched.
    let first = below.split('/').find(|part| !part.is_empty());
    let unread = !target.ends_with(".rs") || matches!(first, Some("target" | ".git"));
    Some(!inside(own) || members.dirs.keys().any(|member| inside(member)) || unread)
}
