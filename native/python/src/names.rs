// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Module names as `source.module_for` and `source.package_for` give them, and the modules that a
//! package of the same name shadows (`explore_scope.parse_unshadowed`, #797).

use std::collections::HashSet;

use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::pyrepr::string;

/// The dotted module of a snapshot path: the path from the first part where the namespace
/// starts, without its last suffix and without a last `__init__`. `None` when the path does not
/// hold the namespace (`module_for` raises `ValueError`).
pub fn module_for(rel: &str, namespace: &str, minor: u32) -> Option<String> {
    let mut parts: Vec<&str> = rel.split('/').filter(|part| !part.is_empty()).collect();
    let last = parts.pop()?;
    parts.push(without_suffix(last, minor)?);
    if parts.last() == Some(&"__init__") {
        parts.pop();
    }
    let prefix: Vec<&str> = namespace.split('.').collect();
    let start = parts
        .windows(prefix.len())
        .position(|window| window == prefix.as_slice())?;
    Some(parts[start..].join("."))
}

/// The name without its suffix, as `PurePath.with_suffix("")` of Python 3.`minor` gives it, or
/// `None` for its `ValueError`. Up to 3.13 the suffix starts at the last dot that is neither the
/// first nor the last character, and 3.13 refuses the stem `.`; 3.14 splits as
/// `os.path.splitext`, where leading dots never start the suffix.
fn without_suffix(name: &str, minor: u32) -> Option<&str> {
    if minor >= 14 {
        let dots = name.len() - name.trim_start_matches('.').len();
        return Some(
            name[dots..]
                .rfind('.')
                .map_or(name, |at| &name[..dots + at]),
        );
    }
    let stem = match name.rfind('.') {
        Some(at) if at > 0 && at + 1 < name.len() => &name[..at],
        _ => name,
    };
    (minor != 13 || stem != ".").then_some(stem)
}

/// `source.package_for`: the first two parts of a module.
pub fn package_for(module: &str) -> String {
    module.splitn(3, '.').take(2).collect::<Vec<_>>().join(".")
}

/// A selected module that a package of the same name shadows: Python imports the package.
#[derive(Clone, Debug, PartialEq)]
pub struct Shadowed {
    pub file: String,
    pub module: String,
}

impl Shadowed {
    /// The text of the gap of `explore_scope._shadowed_gap`.
    pub fn message(&self) -> String {
        format!(
            "module {} is shadowed by the package of the same name and is never imported",
            repr(&self.module)
        )
    }

    pub fn title(&self) -> String {
        format!(
            "{}: module is shadowed by a package of the same name",
            self.file
        )
    }

    pub fn id(&self) -> String {
        let message = self.message();
        let parts = [
            Part::Text(&self.file),
            Part::Number(1),
            Part::Text(SHADOWED_KIND),
            Part::Text(&message),
        ];
        stable_id("COVERAGE", &parts)
    }
}

/// `repr()` of a Python `str`.
fn repr(text: &str) -> String {
    let mut out = String::new();
    string(text, &mut out);
    out
}

pub const SHADOWED_KIND: &str = "ShadowedModule";

/// The selected modules that a package of the same name shadows, in the order of `selected`.
pub fn shadowed(selected: &[String], namespace: &str, minor: u32) -> Vec<Shadowed> {
    let named: Vec<(&String, String)> = selected
        .iter()
        .filter_map(|rel| module_for(rel, namespace, minor).map(|module| (rel, module)))
        .collect();
    let packages: HashSet<&str> = named
        .iter()
        .filter(|(rel, _)| is_package(rel))
        .map(|(_, module)| module.as_str())
        .collect();
    named
        .iter()
        .filter(|(rel, module)| !is_package(rel) && packages.contains(module.as_str()))
        .map(|(rel, module)| Shadowed {
            file: (*rel).clone(),
            module: module.clone(),
        })
        .collect()
}

pub fn is_package(rel: &str) -> bool {
    rel.rsplit('/').next() == Some("__init__.py")
}

#[cfg(test)]
#[path = "names_tests.rs"]
mod tests;
