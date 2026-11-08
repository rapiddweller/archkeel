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

use crate::manifest::{self, Condition, Json, Lookup, Unknown};
use crate::options::{Options, Resolution};
use crate::paths::{basename, dirname, join};
use crate::snapshot::Snapshot;
use crate::source_input::{
    classify_asset, classify_file, classify_specifier, split_file, ModuleFormat, SourceKind,
    SpecifierKind, Suffix,
};

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

/// `_file_paths`: swap a known suffix, then append the permitted suffixes when inference is on.
fn file_paths(candidate: &str, esm: bool, kinds: Kinds) -> Vec<String> {
    let mut paths = Vec::new();
    if let Some((stem, suffix)) = split_file(candidate) {
        paths.extend(
            suffix
                .replacements(kinds)
                .iter()
                .map(|replacement| format!("{stem}{}", replacement.text())),
        );
    }
    if !esm {
        paths.extend(
            Suffix::Absent
                .replacements(kinds)
                .iter()
                .map(|replacement| format!("{candidate}{}", replacement.text())),
        );
    }
    paths
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

    fn modules(
        &mut self,
        snapshot: &mut Snapshot,
        directory: &str,
        specifier: &str,
        esm: bool,
        kinds: Kinds,
    ) -> Lookup<String> {
        let modules = join(directory, "node_modules");
        if !snapshot.is_dir(&modules) {
            return Lookup::Missing;
        }
        let found = self.package(snapshot, &modules, specifier, esm, kinds);
        let types = join(&modules, "@types");
        if found != Lookup::Missing
            || !kinds.contains(&SourceKind::Declaration)
            || !snapshot.is_dir(&types)
        {
            return found;
        }
        let typed = classify_specifier(specifier).typed_name;
        self.package(snapshot, &types, &typed, esm, DECLARATION)
    }

    fn package(
        &mut self,
        snapshot: &mut Snapshot,
        modules: &str,
        specifier: &str,
        esm: bool,
        kinds: Kinds,
    ) -> Lookup<String> {
        let name = classify_specifier(specifier).package;
        let rest = specifier.get(name.len() + 1..).unwrap_or("");
        let root = match self.manifest(snapshot, &join(modules, &name)) {
            Lookup::Unknown(reason) => return Lookup::Unknown(reason),
            Lookup::Hit(root) => Some(root),
            Lookup::Missing => None,
        };
        if root
            .as_ref()
            .is_some_and(|root| root.contains_key("typesVersions"))
        {
            return Lookup::Unknown(Unknown::internal(format!(
                "Package typesVersions are not observed: {name}"
            )));
        }
        if let Some(root) = root
            .as_ref()
            .filter(|root| self.exports_aware() && manifest::declares_exports(root))
        {
            return self.export_target(snapshot, modules, &name, rest, root, esm, kinds);
        }
        let candidate = join(modules, specifier);
        // An ECMAScript import of the package root never infers an extension.
        let file = if !rest.is_empty() || !esm {
            self.file(snapshot, &candidate, esm, kinds)
        } else {
            None
        };
        if file.is_some() || !snapshot.is_dir(&candidate) {
            return file.map_or(Lookup::Missing, Lookup::Hit);
        }
        let nested = if rest.is_empty() {
            None
        } else {
            match self.manifest(snapshot, &candidate) {
                Lookup::Unknown(reason) => return Lookup::Unknown(reason),
                Lookup::Hit(nested) => Some(nested),
                Lookup::Missing => None,
            }
        };
        let manifest = if rest.is_empty() {
            root.as_ref()
        } else {
            nested.as_ref()
        };
        let found = self.worker(snapshot, &candidate, manifest, esm, kinds);
        let defaulted = esm
            && rest.is_empty()
            && root
                .as_ref()
                .is_some_and(|root| !manifest::declares_exports(root));
        if found == Lookup::Missing && defaulted {
            let index = self.file(snapshot, &join(&candidate, "index.js"), esm, kinds);
            return index.map_or(Lookup::Missing, Lookup::Hit);
        }
        found
    }

    /// The small exact `exports` subset that pinned project imports use.
    #[allow(clippy::too_many_arguments)]
    fn export_target(
        &mut self,
        snapshot: &mut Snapshot,
        modules: &str,
        name: &str,
        rest: &str,
        manifest: &Json,
        esm: bool,
        kinds: Kinds,
    ) -> Lookup<String> {
        let exports = manifest.get("exports").unwrap_or(&Value::Null);
        let key = if rest.is_empty() {
            ".".to_owned()
        } else {
            format!("./{rest}")
        };
        let chosen = match manifest::selected(exports, name, rest, &key) {
            Err(reason) => return Lookup::Unknown(reason),
            Ok(None) => return Lookup::Missing,
            Ok(Some(chosen)) => chosen,
        };
        let shown = &key[1..];
        if !(chosen.is_object() || chosen.is_string()) {
            return Lookup::Unknown(Unknown::new(format!(
                "Package exports shape is not observed: {name}"
            )));
        }
        let target = match manifest::condition(chosen, esm) {
            Condition::Unknown(reason) => return Lookup::Unknown(reason),
            Condition::Nothing => {
                return Lookup::Unknown(Unknown::internal(format!(
                    "Package exports conditions are not observed: {name}{shown}"
                )))
            }
            Condition::Target(target) => target,
        };
        if !target.starts_with("./") {
            return Lookup::Unknown(Unknown::new(format!(
                "Package exports target is not package-relative: {name}{shown}"
            )));
        }
        if !manifest::plain_target(&target) {
            return Lookup::Unknown(Unknown::new(format!(
                "Package exports target path is not observed: {name}{shown}"
            )));
        }
        let candidate = join(&join(modules, name), &target[2..]);
        // Only a recognized TypeScript or declaration target names its exact source file.
        let exact = classify_file(&target)
            .and_then(Suffix::source_kind)
            .is_some_and(|kind| matches!(kind, SourceKind::TypeScript | SourceKind::Declaration));
        let paths = if exact {
            vec![candidate.clone()]
        } else {
            file_paths(&candidate, true, kinds)
        };
        for path in paths {
            if snapshot.is_file(&path) {
                return Lookup::Hit(path);
            }
        }
        if self.options.resolution() == Resolution::Bundler
            && classify_asset(&target).is_some()
            && snapshot.is_file(&candidate)
        {
            // A bundler loads an exported asset itself; the package is the dependency.
            return Lookup::Unknown(Unknown::internal(format!(
                "Package exports target is an asset: {name}{shown}"
            )));
        }
        Lookup::Unknown(Unknown::new(format!(
            "Package exports target is unavailable: {name}{shown}"
        )))
    }

    fn by_name(
        &mut self,
        snapshot: &mut Snapshot,
        candidate: &str,
        directory_only: bool,
        esm: bool,
        kinds: Kinds,
        package: bool,
    ) -> Lookup<String> {
        let found = if directory_only {
            None
        } else {
            self.file(snapshot, candidate, esm, kinds)
        };
        // ECMAScript modules never import a directory.
        if found.is_some() || esm || !snapshot.is_dir(candidate) {
            return found.map_or(Lookup::Missing, Lookup::Hit);
        }
        let manifest = if package {
            match self.manifest(snapshot, candidate) {
                Lookup::Unknown(reason) => return Lookup::Unknown(reason),
                Lookup::Hit(manifest) => Some(manifest),
                Lookup::Missing => None,
            }
        } else {
            None
        };
        self.worker(snapshot, candidate, manifest.as_ref(), esm, kinds)
    }

    fn file(
        &mut self,
        snapshot: &mut Snapshot,
        candidate: &str,
        esm: bool,
        kinds: Kinds,
    ) -> Option<String> {
        file_paths(candidate, esm, kinds)
            .into_iter()
            .find(|path| snapshot.is_file(path))
    }

    /// A package directory: the file that `types` or `main` names, else its `index`.
    fn worker(
        &mut self,
        snapshot: &mut Snapshot,
        directory: &str,
        manifest: Option<&Json>,
        esm: bool,
        kinds: Kinds,
    ) -> Lookup<String> {
        let empty = Json::new();
        let fields = manifest.unwrap_or(&empty);
        if fields.contains_key("typesVersions") {
            let installed = directory
                .split('/')
                .any(|segment| segment == "node_modules");
            let reason = format!("Package typesVersions are not observed: {directory}");
            return Lookup::Unknown(Unknown {
                reason,
                package_internal: installed,
            });
        }
        let keys: &[&str] = if kinds.contains(&SourceKind::Declaration) {
            &["typings", "types", "main"]
        } else {
            &["main"]
        };
        let named = keys.iter().find_map(|key| {
            fields
                .get(*key)
                .and_then(Value::as_str)
                .filter(|v| !v.is_empty())
        });
        if let Some(named) = named {
            let target = join(directory, named);
            let suffix = classify_file(&target).and_then(Suffix::source_kind);
            if suffix.is_some_and(|kind| kinds.contains(&kind)) && snapshot.is_file(&target) {
                return Lookup::Hit(target);
            }
            // A package that is not itself ECMAScript may name a file without its extension.
            let strict = esm && manifest::is_module(fields);
            let expanded = if kinds == DECLARATION {
                TS_AND_DECLARATION
            } else {
                kinds
            };
            if let Some(found) = self
                .by_name(snapshot, &target, false, strict, expanded, false)
                .stops()
            {
                return found;
            }
        }
        self.file(snapshot, &join(directory, "index"), esm, kinds)
            .map_or(Lookup::Missing, Lookup::Hit)
    }
}

#[cfg(test)]
#[path = "resolve_tests.rs"]
mod tests;
