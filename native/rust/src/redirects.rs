// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Whether a registry or git dependency can be redirected to a path (AD-502).
//!
//! Cargo can point a registry name at a local crate: `[patch]` and `[replace]` in the manifest of
//! the crate or of its workspace root (also a root named by `package.workspace`), and `[patch]`,
//! `paths` and `[source]` in a `.cargo/config.toml` of the crate directory or any directory above
//! it. The collector reads each of these places below the scan root. A place that it cannot
//! read gives a named gap. A place outside the scan root (`$CARGO_HOME/config.toml`, a root
//! above the scan root) and the `CARGO_*` environment stay unread: `docs/known-limits.md`.

use std::collections::BTreeMap;
use std::rc::Rc;

use crate::crates::Parsed;
use crate::manifest::get;
use crate::source::read_text;
use crate::toml::{self, Table};
use archkeel_snapshot::paths::{dirname, is_outside, join};
use archkeel_snapshot::Snapshot;

/// The tables that redirect a dependency.
const REDIRECTS: [&str; 3] = ["patch", "replace", "paths"];
/// The cargo config files of one directory, in the order that Cargo prefers.
const CONFIGS: [&str; 2] = [".cargo/config.toml", ".cargo/config"];

/// What the places that can redirect a dependency say.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Redirect {
    /// Every place was read and none redirects: a registry name is not a crate of the workspace.
    None,
    /// A place redirects, or may redirect, a name: the old rule (a name of the workspace is an
    /// edge) stays.
    Possible,
    /// A place that Cargo reads could not be read: the reason, for a gap.
    Unread(String),
}

fn redirects(table: &Table) -> bool {
    REDIRECTS.iter().any(|key| table.contains_key(*key)) || table.contains_key("source")
}

/// The places of the manifest of `dir`: its own tables, the workspace root above it (`above`), the
/// root that `package.workspace` names, and the cargo configs from `dir` up to the scan root.
pub(crate) fn of(
    source: &mut Snapshot,
    tables: &mut BTreeMap<String, Option<Rc<Parsed>>>,
    (dir, table): (&str, &Table),
    above: Option<&Parsed>,
) -> Redirect {
    let manifests = |table: &Table| {
        ["patch", "replace"]
            .iter()
            .any(|key| table.contains_key(*key))
    };
    if manifests(table) || above.is_some_and(|above| manifests(&above.table)) {
        return Redirect::Possible;
    }
    if let Some(pointer) = get(table, &["package", "workspace"]).and_then(|v| v.text()) {
        let root = join(dir, pointer);
        let root = if root == "." { String::new() } else { root };
        if is_outside(&root) {
            return Redirect::Unread(format!(
                "The workspace root {pointer} of the crate in {dir} lies outside the scan root"
            ));
        }
        match crate::crates::manifest_table(source, tables, &root) {
            Ok(Some(named)) if manifests(&named.table) => return Redirect::Possible,
            Ok(Some(_)) => {}
            Ok(None) | Err(_) => {
                return Redirect::Unread(format!(
                    "The workspace root {root} of the crate in {dir} cannot be read"
                ))
            }
        }
    }
    configs(source, dir)
}

/// The cargo config files of `dir` and of each directory above it, up to the scan root.
fn configs(source: &mut Snapshot, dir: &str) -> Redirect {
    let mut at = dir.to_owned();
    loop {
        for name in CONFIGS {
            let rel = join(&at, name);
            if !source.is_file(&rel) {
                continue;
            }
            let read = read_text(source, &rel).and_then(|text| {
                toml::parse(&text).map_err(|error| format!("Cannot read {rel}: {error}"))
            });
            match read {
                Ok(table) if redirects(&table) => return Redirect::Possible,
                Ok(_) => {}
                Err(reason) => return Redirect::Unread(reason),
            }
        }
        if at.is_empty() {
            return Redirect::None;
        }
        at = dirname(&at).to_owned();
    }
}

#[cfg(test)]
#[path = "redirects_tests.rs"]
mod tests;
