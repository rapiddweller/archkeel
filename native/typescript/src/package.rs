// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package side of the resolver: `node_modules`, `@types`, `exports`, `main` and `types`.

use serde_json::Value;

use super::{Resolver, DECLARATION, TS_AND_DECLARATION};
use crate::manifest::{self, Condition, Json, Lookup, Unknown};
use crate::options::Resolution;
use crate::paths::join;
use crate::snapshot::Snapshot;
use crate::source_input::{
    classify_asset, classify_file, classify_specifier, split_file, SourceKind, Suffix,
};

type Kinds<'a> = &'a [SourceKind];

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

impl Resolver {
    pub(super) fn modules(
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
    #[expect(
        clippy::too_many_arguments,
        reason = "eight parameters with self: group them in a context struct (AD-327)"
    )]
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

    pub(super) fn by_name(
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
