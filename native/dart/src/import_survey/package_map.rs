// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The package map of the root package (AD-800): for each package that a `package:` URI names,
//! whether the survey proves it external (pub-hosted, from the SDK, or from a remote git
//! repository) or not.
//!
//! `pub` resolves a package name only from the root `pubspec.yaml` (its dependencies, its overrides
//! and its workspace) and from `.dart_tool/package_config.json`, which `pub get` writes from them
//! and which keeps its own check (`config.rs`, AD-454). A package that is neither proven external nor the own package keeps a named gap at each import
//! of it: the edges of that library are unknown. A local package that no library imports adds no
//! edge, so it needs no gap (#1539). A package that no dependency declares is transitive: it is
//! external unless a local dependency declares it by its own path. A hosted or SDK package
//! cannot have a path dependency, and the path of a remote git package stays in its repository.

use std::collections::{BTreeMap, BTreeSet};

use super::names::GapName;

/// Where `pub` takes a declared dependency from.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Origin {
    /// pub.dev or another package server.
    Hosted,
    /// The Dart or Flutter SDK.
    Sdk,
    /// A git repository with a remote URL: `pub` copies it into its cache.
    RemoteGit,
    /// A path, a git repository with a local URL, or a form that the survey does not read.
    Local(&'static str),
}

/// The package map of one survey. `Default` is the map of an unreadable root `pubspec.yaml`:
/// its whole-scope package gap already holds every edge, so no import needs one more.
#[derive(Debug, Default)]
pub(crate) struct PackageMap {
    /// The map is read: each import of another package is classified.
    pub(crate) read: bool,
    /// The origin of each declared dependency; an override replaces the dependency.
    pub(crate) declared: BTreeMap<String, Origin>,
    /// The members of a workspace that the root `pubspec.yaml` declares.
    pub(crate) members: BTreeSet<String>,
    /// The root package is a member of a workspace that the survey cannot read, which can resolve
    /// any package name to another member or override it.
    pub(crate) unseen_workspace: bool,
    /// The names that a member of the workspace above the package declares with a local origin.
    pub(crate) local_names: BTreeSet<String>,
    /// The directory of the workspace root above the package, when the survey read it (#1539).
    pub(crate) workspace_root: Option<String>,
}

impl PackageMap {
    /// `Ok` when `package` is proven external; else the gap of each import of it.
    pub(crate) fn external(&self, package: &str) -> Result<(), (GapName, String)> {
        if !self.read {
            return Ok(());
        }
        let local = |why: &str| Err((GapName::LocalPackage, format!("{package}: {why}")));
        if self.unseen_workspace {
            return local("the package is a member of a workspace above the root; that workspace can resolve or override this name");
        }
        if self.members.contains(package) {
            return local("a member of the workspace; its URIs are not resolved");
        }
        if self.local_names.contains(package) {
            return local("a member of the workspace declares it with a local origin");
        }
        match self.declared.get(package) {
            Some(Origin::Local(why)) => local(why),
            Some(_) => Ok(()),
            // A transitive dependency: only a local package can make it local, by its own path.
            None if !self.local_names.is_empty()
                || self.declared.values().any(|origin| matches!(origin, Origin::Local(_))) =>
            {
                Err((
                    GapName::UndeclaredPackage,
                    format!("{package}: no dependency of the package pubspec.yaml declares it, and a local dependency can make it local"),
                ))
            }
            None => Ok(()),
        }
    }

    /// `Ok` when a `package:` URI of the own package names a file of this root: a workspace above
    /// the root can override any name, the own one too.
    pub(crate) fn own(&self, package: &str) -> Result<(), (GapName, String)> {
        if self.read && self.unseen_workspace {
            return Err((
                GapName::LocalPackage,
                format!("{package}: the package is a member of a workspace above the root; that workspace can override this name"),
            ));
        }
        Ok(())
    }
}

/// The origin of a dependency from the keys of its mapping. `keys` holds each key with its text
/// value (`None` for a value that is no text).
pub(crate) fn origin(keys: &[(&str, Option<&str>)]) -> Origin {
    let has = |name: &str| keys.iter().any(|(key, _)| *key == name);
    let text = |name: &str| {
        keys.iter()
            .find(|(key, _)| *key == name)
            .and_then(|(_, value)| *value)
    };
    let known = keys
        .iter()
        .all(|(key, _)| matches!(*key, "sdk" | "hosted" | "version" | "git" | "path"));
    if !known {
        return Origin::Local("the dependency has a key that the survey does not read");
    }
    if has("path") {
        return Origin::Local("the dependency has a local path; its URIs are not resolved");
    }
    if has("git") {
        return match text("git") {
            Some(url) if remote(url) => Origin::RemoteGit,
            Some(_) => Origin::Local("the git URL is local; its URIs are not resolved"),
            // A git mapping: its `url` is read by `git_url`.
            None => Origin::Local("the git dependency is not read"),
        };
    }
    if has("sdk") {
        return Origin::Sdk;
    }
    Origin::Hosted
}

/// A git URL that names a remote repository.
pub(crate) fn remote(url: &str) -> bool {
    let lower = url.to_ascii_lowercase();
    ["https://", "http://", "ssh://", "git://", "git+ssh://"]
        .iter()
        .any(|scheme| lower.starts_with(scheme))
        || (lower.starts_with("git@") && lower.contains(':'))
}

#[cfg(test)]
#[path = "package_map_tests.rs"]
mod tests;
