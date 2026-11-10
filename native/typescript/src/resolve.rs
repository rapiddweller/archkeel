// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Resolve module specifiers to snapshot files, never to a guess (`resolve.py`).
//!
//! Each rule is a transcription of what the TypeScript compiler does for the case it covers.
//! A specifier or a setting outside those rules is `Unknown` with its reason: a resolver that is
//! more permissive than the compiler would turn an unresolvable import into a proven dependency.

use std::collections::HashSet;

use serde_json::Value;

use crate::manifest::{self, Json, Lookup, Unknown};
use crate::options::{Options, Resolution};
use crate::source_input::{
    classify_file, classify_specifier, ModuleFormat, SourceKind, SpecifierKind, Suffix,
};
use archkeel_snapshot::paths::{basename, dirname, join};
use archkeel_snapshot::Snapshot;

/// A file that a specifier names.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Found {
    pub path: String,
    /// Reached through a `node_modules` search, so it is a dependency wherever the file lives.
    pub external: bool,
    /// A directory's `package.json` decided the file; Node may load another one.
    pub directory_package: bool,
    /// Matched a `paths` entry, which a bundler alias is assumed to mirror.
    pub via_paths: bool,
}

type Kinds<'a> = &'a [SourceKind];
const TS_AND_DECLARATION: Kinds = &[SourceKind::TypeScript, SourceKind::Declaration];
const DECLARATION: Kinds = &[SourceKind::Declaration];

pub struct Resolver {
    pub options: Options,
    partial: bool,
    /// A reason that nothing can be resolved: the settings in force are not all understood.
    pub blocked: Option<Unknown>,
    reads: HashSet<String>,
}

/// The directories from the one that holds `rel` up to the snapshot root.
fn ancestors(rel: &str) -> Vec<String> {
    let first = dirname(rel);
    let mut chain = vec![if first.is_empty() { "." } else { first }.to_owned()];
    while chain.last().is_some_and(|last| last != ".") {
        let next = dirname(chain.last().map_or("", String::as_str));
        chain.push(if next.is_empty() { "." } else { next }.to_owned());
    }
    chain
}

fn importer_directory(importer: &str) -> String {
    match dirname(importer) {
        "" => ".".to_owned(),
        directory => directory.to_owned(),
    }
}

/// `_best_pattern`: the exact `paths` key, else the longest prefix; the text the star matched.
fn best_pattern<'a>(
    patterns: &'a [(String, Vec<String>)],
    specifier: &str,
) -> Option<(String, &'a [String])> {
    let mut best: Option<(usize, String, &[String])> = None;
    for (pattern, targets) in patterns {
        if pattern == specifier {
            return Some((String::new(), targets));
        }
        let Some((prefix, suffix)) = pattern.split_once('*') else {
            continue;
        };
        let fits = specifier.len() >= prefix.len() + suffix.len()
            && specifier.starts_with(prefix)
            && specifier.ends_with(suffix);
        let length = prefix.chars().count();
        if fits && best.as_ref().is_none_or(|(known, _, _)| length > *known) {
            let star = &specifier[prefix.len()..specifier.len() - suffix.len()];
            best = Some((length, star.to_owned(), targets));
        }
    }
    best.map(|(_, star, targets)| (star, targets))
}

/// The compiler substitutes only a non-empty match and keeps the text otherwise.
fn substitute(target: &str, star: &str) -> String {
    if star.is_empty() {
        target.to_owned()
    } else {
        target.replacen('*', star, 1)
    }
}

/// `_package_subpath`: the path inside a package, `None` when it holds a `.` or `..` segment.
fn package_subpath<'a>(specifier_path: &'a str, name: &str) -> Option<&'a str> {
    let subpath = specifier_path.get(name.len()..)?.strip_prefix('/')?;
    (!subpath
        .split('/')
        .any(|segment| matches!(segment, "." | "..")))
    .then_some(subpath)
}

impl Resolver {
    pub fn new(options: Options, partial: bool) -> Self {
        let mut resolver = Self {
            options,
            partial,
            blocked: None,
            reads: HashSet::new(),
        };
        resolver.blocked = resolver.blocked_reason();
        resolver
    }

    fn blocked_reason(&self) -> Option<Unknown> {
        if !self.options.unmodeled.is_empty() {
            let names = self.options.unmodeled.join(", ");
            return Some(Unknown::new(format!(
                "Compiler option is not observed: {names}"
            )));
        }
        if self.partial {
            return Some(Unknown::new("TSConfig settings are not fully observed"));
        }
        (self.options.resolution() == Resolution::Classic)
            .then(|| Unknown::new("moduleResolution classic is not observed"))
    }

    fn exports_aware(&self) -> bool {
        matches!(
            self.options.resolution(),
            Resolution::Node16 | Resolution::NodeNext | Resolution::Bundler
        )
    }

    fn manifest(&mut self, snapshot: &mut Snapshot, directory: &str) -> Lookup<Json> {
        let (path, found) = manifest::read(snapshot, directory);
        self.reads.extend(path);
        found
    }

    /// The nearest `package.json` above a file, searched up to the filesystem root.
    pub fn scope(&mut self, snapshot: &mut Snapshot, rel: &str) -> Lookup<Json> {
        let mut chain = ancestors(rel);
        chain.extend((1..=snapshot.depth()).map(|level| vec![".."; level].join("/")));
        for current in chain {
            if basename(&current) == "node_modules" {
                continue;
            }
            if let Some(found) = self.manifest(snapshot, &current).stops() {
                return found;
            }
        }
        Lookup::Missing
    }

    /// Whether Node loads a file as ESM or CommonJS; `Missing` where no format is defined.
    pub fn format_of(&mut self, snapshot: &mut Snapshot, rel: &str) -> Lookup<ModuleFormat> {
        if !matches!(
            self.options.resolution(),
            Resolution::Node16 | Resolution::NodeNext
        ) {
            return Lookup::Missing;
        }
        let suffix = classify_file(rel);
        if !suffix.is_some_and(Suffix::scoped_format) {
            return suffix
                .and_then(Suffix::format_hint)
                .map_or(Lookup::Missing, Lookup::Hit);
        }
        match self.scope(snapshot, rel) {
            Lookup::Unknown(reason) => Lookup::Unknown(reason),
            Lookup::Hit(manifest) if manifest::is_module(&manifest) => {
                Lookup::Hit(ModuleFormat::Esm)
            }
            _ => Lookup::Hit(ModuleFormat::Cjs),
        }
    }

    /// The snapshot file that `specifier` names, `Missing` when it names none.
    #[expect(
        clippy::excessive_nesting,
        reason = "the function nests blocks deeper than 4: flatten it (AD-327)"
    )]
    pub fn resolve(
        &mut self,
        snapshot: &mut Snapshot,
        specifier: &str,
        importer: &str,
        mode: Option<ModuleFormat>,
        prefer_builtin: bool,
    ) -> Lookup<Found> {
        self.reads.clear();
        let source = classify_specifier(specifier);
        let esm = mode == Some(ModuleFormat::Esm);
        let node10 = self.options.resolution() == Resolution::Node10;
        // Under Node10 the compiler looks for TypeScript everywhere before it looks for
        // JavaScript. JSON modules are tried with the JavaScript files, which come last.
        let last: &[SourceKind] = if self.options.resolve_json() {
            &[SourceKind::JavaScript, SourceKind::Json]
        } else {
            &[SourceKind::JavaScript]
        };
        let all = [TS_AND_DECLARATION, last].concat();
        let passes: Vec<Kinds> = if node10 {
            vec![TS_AND_DECLARATION, last]
        } else {
            vec![&all]
        };
        if source.relative() {
            let candidate = join(&importer_directory(importer), specifier);
            for kinds in passes {
                let found = self.by_name(
                    snapshot,
                    &candidate,
                    source.directory_only,
                    esm,
                    kinds,
                    true,
                );
                if let Some(found) = found.stops() {
                    return self.found(snapshot, found, false, Some(&candidate), false);
                }
            }
            return Lookup::Missing;
        }
        if specifier.starts_with('/') {
            return Lookup::Unknown(Unknown::new(format!(
                "Absolute specifiers are not observed: {specifier}"
            )));
        }
        for kinds in passes {
            if let Some((found, lookup, via_paths)) = self.mapped(snapshot, specifier, esm, kinds) {
                return self.found(snapshot, found, false, lookup.as_deref(), via_paths);
            }
            let node_modes = matches!(
                self.options.resolution(),
                Resolution::Node16 | Resolution::NodeNext
            );
            if prefer_builtin && mode.is_some() && node_modes && source.builtin() {
                return Lookup::Missing;
            }
            // The project's own names come first, then `imports`, then the package itself.
            if self.exports_aware() && source.kind == SpecifierKind::Imports {
                return Lookup::Unknown(Unknown::new(format!(
                    "Package imports are not observed: {specifier}"
                )));
            }
            if self.exports_aware() && self.self_reference(snapshot, importer, &source.package) {
                return Lookup::Unknown(Unknown::new(format!(
                    "Package self-reference is not observed: {specifier}"
                )));
            }
            for directory in ancestors(importer) {
                let found = self.modules(snapshot, &directory, specifier, esm, kinds);
                if let Some(found) = found.stops() {
                    return self.found(snapshot, found, true, None, false);
                }
            }
        }
        Lookup::Missing
    }

    /// `paths`, then `baseUrl`: the project's own names, tried before packages.
    ///
    /// The result, the directory that a `package.json` may have decided, and whether `paths`
    /// matched.
    #[expect(
        clippy::excessive_nesting,
        reason = "the function nests blocks deeper than 4: flatten it (AD-327)"
    )]
    fn mapped(
        &mut self,
        snapshot: &mut Snapshot,
        specifier: &str,
        esm: bool,
        kinds: Kinds,
    ) -> Option<(Lookup<String>, Option<String>, bool)> {
        let matched = best_pattern(&self.options.paths, specifier)
            .map(|(star, targets)| (star, targets.to_vec()));
        let paths_base = self.options.paths_base.clone();
        if let Some((star, targets)) = matched {
            for target in &targets {
                if target.starts_with('/') {
                    let reason = format!("Absolute paths targets are not observed: {specifier}");
                    return Some((Lookup::Unknown(Unknown::new(reason)), None, true));
                }
                let candidate = join(&paths_base, &substitute(target, &star));
                // A target that names its extension is a file, not a name to complete.
                let named = !matches!(classify_file(target), None | Some(Suffix::Absent));
                if named && snapshot.is_file(&candidate) {
                    return Some((Lookup::Hit(candidate), None, true));
                }
                let found = self.by_name(snapshot, &candidate, false, esm, kinds, true);
                if let Some(found) = found.stops() {
                    return Some((found, Some(candidate), true));
                }
            }
        }
        let base = self.options.base_url.clone()?;
        let lookup = join(&base, specifier);
        let found = self
            .by_name(snapshot, &lookup, false, esm, kinds, true)
            .stops()?;
        Some((found, Some(lookup), false))
    }

    fn found(
        &mut self,
        snapshot: &mut Snapshot,
        found: Lookup<String>,
        external: bool,
        lookup: Option<&str>,
        via_paths: bool,
    ) -> Lookup<Found> {
        let path = match found {
            Lookup::Hit(path) => path,
            Lookup::Unknown(reason) => return Lookup::Unknown(reason),
            Lookup::Missing => return Lookup::Missing,
        };
        let directory = lookup.is_some_and(|lookup| {
            self.reads.contains(&join(lookup, "package.json")) && snapshot.is_dir(lookup)
        });
        Lookup::Hit(Found {
            path: snapshot.real(&path).unwrap_or(path),
            external,
            directory_package: directory,
            via_paths,
        })
    }

    /// Whether a relative specifier names a file in the snapshot, with no extension search.
    pub fn file_exists(
        &self,
        snapshot: &mut Snapshot,
        importer: &str,
        specifier_path: &str,
    ) -> bool {
        snapshot.is_file(&join(&importer_directory(importer), specifier_path))
    }

    /// Whether an installed package holds the file that a package subpath names, inside itself.
    pub fn package_file_exists(
        &self,
        snapshot: &mut Snapshot,
        importer: &str,
        specifier_path: &str,
    ) -> bool {
        let name = classify_specifier(specifier_path).package;
        let Some(subpath) = package_subpath(specifier_path, &name) else {
            return false;
        };
        ancestors(importer).iter().any(|directory| {
            let package = join(&join(directory, "node_modules"), &name);
            snapshot.is_dir(&package) && snapshot.is_file(&join(&package, subpath))
        })
    }

    /// Whether a `paths` entry maps a specifier onto an existing file.
    pub fn alias_file_exists(&self, snapshot: &mut Snapshot, specifier_path: &str) -> bool {
        let Some((star, targets)) = best_pattern(&self.options.paths, specifier_path) else {
            return false;
        };
        targets.iter().any(|target| {
            !target.starts_with('/')
                && snapshot.is_file(&join(&self.options.paths_base, &substitute(target, &star)))
        })
    }

    fn self_reference(&mut self, snapshot: &mut Snapshot, importer: &str, name: &str) -> bool {
        matches!(
            self.scope(snapshot, importer),
            Lookup::Hit(manifest)
                if manifest.get("name").and_then(Value::as_str) == Some(name)
                    && manifest::declares_exports(&manifest)
        )
    }
}

#[path = "package.rs"]
mod package;

#[cfg(test)]
#[path = "resolve_tests.rs"]
mod tests;
