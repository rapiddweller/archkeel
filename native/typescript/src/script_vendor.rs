// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The globals that vendored libraries publish (`collect._script_vendor_publications` and
//! `resolve.Resolver.script_provider`). A library counts only when its provenance file names the
//! package and the digest of the exact bytes of its source.

use std::collections::{BTreeSet, HashMap, HashSet};

use archkeel_facts::identity::sha256_hex;
use archkeel_snapshot::Snapshot;

use crate::options::Options;
use crate::pytext::decode;
use crate::script_environment::{ScriptEnvironment, ScriptProvider};
use crate::script_project::LOADER_NAMES;
use crate::syntax::Parsers;
use crate::umd_publication::publication;

/// The globals that the declared vendors publish.
#[derive(Default)]
pub struct Vendors {
    /// The packages that publish each name.
    pub packages: HashMap<String, Vec<String>>,
    /// Every provider was read and published one name.
    pub complete: bool,
    /// The names that the vendors write on the global object.
    pub writes: HashSet<String>,
    /// A vendor may write names that the file cannot know.
    pub unbounded: bool,
}

/// What the resolver may use to read a provider.
pub struct Setting<'a> {
    pub environment: &'a ScriptEnvironment,
    pub options: &'a Options,
    pub partial: bool,
}

/// `str.splitlines` for the separators that a provenance file can hold.
fn split_lines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((at, c)) = chars.next() {
        let breaks = matches!(
            c,
            '\n' | '\r'
                | '\u{b}'
                | '\u{c}'
                | '\u{1c}'
                | '\u{1d}'
                | '\u{1e}'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        );
        if !breaks {
            continue;
        }
        lines.push(text.get(start..at).unwrap_or(""));
        let crlf = c == '\r' && chars.peek().is_some_and(|(_, next)| *next == '\n');
        if crlf {
            chars.next();
        }
        start = at
            .saturating_add(c.len_utf8())
            .saturating_add(usize::from(crlf));
    }
    if start < text.len() {
        lines.push(text.get(start..).unwrap_or(""));
    }
    lines
}

/// `[a-z0-9][a-z0-9._-]*`.
fn is_name(text: &str) -> bool {
    let mut chars = text.chars();
    let lower = |c: char| c.is_ascii_lowercase() || c.is_ascii_digit();
    chars.next().is_some_and(lower) && chars.all(|c| lower(c) || matches!(c, '.' | '_' | '-'))
}

/// An npm package name: a name, or `@scope/name`.
fn is_package(text: &str) -> bool {
    match text.strip_prefix('@') {
        Some(scoped) => scoped
            .split_once('/')
            .is_some_and(|(scope, name)| is_name(scope) && is_name(name)),
        None => is_name(text),
    }
}

/// `\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?`.
fn is_version(text: &str) -> bool {
    let (core, rest) = match text.find(['-', '+']) {
        Some(at) => text.split_at(at),
        None => (text, ""),
    };
    let numbers: Vec<&str> = core.split('.').collect();
    let digits = |s: &&str| !s.is_empty() && s.chars().all(|c| c.is_ascii_digit());
    let tag = |s: &str| {
        !s.is_empty()
            && s.chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-'))
    };
    let suffix = match (rest.strip_prefix('-'), rest.strip_prefix('+')) {
        (Some(pre), _) => match pre.split_once('+') {
            Some((pre, build)) => tag(pre) && tag(build),
            None => tag(pre),
        },
        (None, Some(build)) => tag(build),
        _ => rest.is_empty(),
    };
    numbers.len() == 3 && numbers.iter().all(digits) && suffix
}

/// The package and the version in `Vendored from `pkg@1.2.3` (`path`), https://host/path.`.
fn vendored(line: &str) -> Option<(&str, &str)> {
    let rest = line.strip_prefix("Vendored from `")?;
    let (spec, rest) = rest.split_once('`')?;
    let (package, version) = spec.rsplit_once('@').filter(|(p, _)| !p.is_empty())?;
    let rest = rest.strip_prefix(" (`")?;
    let (file, rest) = rest.split_once("`), https://")?;
    let url = rest.strip_suffix('.')?;
    let simple = |s: &str| !s.is_empty() && !s.chars().any(char::is_whitespace);
    let named = is_package(package) && is_version(version);
    (named && simple(file) && !file.contains('`') && simple(url)).then_some((package, version))
}

/// `Bundle SHA-256: `<64 hex digits>`.`
fn bundle_digest(line: &str) -> Option<&str> {
    let digest = line.strip_prefix("Bundle SHA-256: `")?.strip_suffix("`.")?;
    let lower_hex = digest
        .chars()
        .all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c));
    (digest.len() == 64 && lower_hex).then_some(digest)
}

/// `SPDX license: `[A-Za-z0-9.+() -]+`.`
fn is_license(line: &str) -> bool {
    let Some(name) = line
        .strip_prefix("SPDX license: `")
        .and_then(|s| s.strip_suffix("`."))
    else {
        return false;
    };
    !name.is_empty()
        && name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '+' | '(' | ')' | ' ' | '-'))
}

/// `resolve.Resolver.script_provider`: the package and the bytes of a declared vendor.
fn provider(
    snapshot: &mut Snapshot,
    setting: &Setting,
    declared: &ScriptProvider,
) -> Option<(String, Vec<u8>)> {
    let options = setting.options;
    let blocked = !setting.environment.classic_browser
        || !setting.environment.providers.contains(declared)
        || setting.partial
        || !options.unmodeled.is_empty()
        || options.lib_unmodeled;
    if blocked {
        return None;
    }
    let content = snapshot.read(&declared.source)?;
    let provenance = snapshot.read(&declared.provenance)?;
    let raw = decode(&provenance);
    let text = raw.trim_start_matches('\u{feff}');
    let lines = split_lines(text);
    let counted = text
        .split('\n')
        .filter(|line| line.starts_with("Bundle SHA-256:"))
        .count();
    if lines.len() < 5 || counted != 1 {
        return None;
    }
    let (package, version) = vendored(lines.get(2)?)?;
    let digest = bundle_digest(lines.get(3)?)?;
    let title = lines.first()?.strip_prefix("# ")?;
    let suffix = format!(" {version} browser bundle");
    let titled = title
        .strip_suffix(suffix.as_str())
        .is_some_and(|name| !name.is_empty());
    (titled && is_license(lines.get(4)?) && sha256_hex(&content) == digest)
        .then(|| (package.to_owned(), content))
}

/// `collect._script_vendor_publications`.
pub fn read(snapshot: &mut Snapshot, parsers: &mut Parsers, setting: &Setting) -> Vendors {
    let mut found = Vendors::default();
    let mut packages: HashMap<String, Vec<String>> = HashMap::new();
    for declared in &setting.environment.providers {
        let Some((package, content)) = provider(snapshot, setting, declared) else {
            return found;
        };
        let Some(item) = publication(parsers, &declared.source, &content) else {
            return found;
        };
        if LOADER_NAMES.contains(&item.name.as_str()) {
            return found;
        }
        packages.entry(item.name).or_default().push(package);
        match item.writes {
            None => found.unbounded = true,
            Some(writes) => found.writes.extend(writes_of(writes)),
        }
    }
    found.packages = packages;
    found.complete = true;
    found
}

fn writes_of(writes: BTreeSet<String>) -> impl Iterator<Item = String> {
    writes.into_iter()
}

#[cfg(test)]
#[path = "script_vendor_tests.rs"]
mod tests;
