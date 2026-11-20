// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Module names as `source.module_for` and `source.package_for` give them, and the modules that a
//! package of the same name shadows (`explore_scope.parse_unshadowed`, #797).

use std::collections::HashSet;

use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::pyminor::PyMinor;
use archkeel_facts::pyrepr::string;

/// The dotted module of a snapshot path: the path from the first part where the namespace
/// starts, without its last suffix and without a last `__init__`. `None` when the path does not
/// hold the namespace (`module_for` raises `ValueError`).
pub(crate) fn module_for(rel: &str, namespace: &str, minor: PyMinor) -> Option<String> {
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

/// A Python name below an import root, or an existing namespace-relative name.
pub(crate) fn scoped(
    rel: &str,
    namespace: &str,
    roots: &[String],
    minor: PyMinor,
) -> Option<String> {
    if !namespace.is_empty() {
        return module_for(rel, namespace, minor);
    }
    let path = roots.iter().find_map(|root| below_root(rel, root))?;
    let (directory, leaf) = path.rsplit_once('/').unwrap_or(("", path));
    let stem = without_suffix(leaf, minor)?;
    if directory.is_empty() {
        Some(stem.to_owned())
    } else if stem == "__init__" {
        Some(directory.replace('/', "."))
    } else {
        Some(format!("{}.{}", directory.replace('/', "."), stem))
    }
}

pub(crate) fn below_root<'a>(rel: &'a str, root: &str) -> Option<&'a str> {
    if root == "." {
        Some(rel)
    } else {
        rel.strip_prefix(root.trim_start_matches("./").trim_end_matches('/'))?
            .strip_prefix('/')
    }
}

/// The source path of an importable module or package must match its dotted name.
pub(crate) fn importable_path(rel: &str, module: &str) -> bool {
    let Some(stem) = rel.strip_suffix(".py") else {
        return false;
    };
    let matches = |path: &str| {
        let mut components = path.rsplit('/');
        module.rsplit('.').all(|name| {
            archkeel_facts::identity::is_identifier(name) && components.next() == Some(name)
        })
    };
    matches(stem) || stem.strip_suffix("/__init__").is_some_and(matches)
}

/// The name without its suffix, as `PurePath.with_suffix("")` of Python 3.`minor` gives it, or
/// `None` for its `ValueError`. Up to 3.13 the suffix starts at the last dot that is neither the
/// first nor the last character, and 3.13 refuses the stem `.`; 3.14 splits as
/// `os.path.splitext`, where leading dots never start the suffix.
fn without_suffix(name: &str, minor: PyMinor) -> Option<&str> {
    if match minor {
        PyMinor::Py311 | PyMinor::Py312 | PyMinor::Py313 => false,
        PyMinor::Py314 => true,
    } {
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
    match minor {
        PyMinor::Py311 | PyMinor::Py312 | PyMinor::Py314 => Some(stem),
        PyMinor::Py313 => (stem != ".").then_some(stem),
    }
}

/// `source.package_for`: the first two parts of a module.
pub(crate) fn package_for(module: &str) -> String {
    module.splitn(3, '.').take(2).collect::<Vec<_>>().join(".")
}

/// A selected module that a package in the same directory shadows.
pub(crate) struct Shadowed {
    pub file: String,
    pub module: String,
}

impl Shadowed {
    /// The text of the gap of `explore_scope._shadowed_gap`.
    pub(crate) fn message(&self) -> String {
        format!(
            "module {} is shadowed by the package of the same name and is never imported",
            repr(&self.module)
        )
    }

    pub(crate) fn title(&self) -> String {
        format!(
            "{}: module is shadowed by a package of the same name",
            self.file
        )
    }

    pub(crate) fn id(&self) -> String {
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

const SHADOWED_KIND: &str = "ShadowedModule";

/// The selected modules that a package in the same directory shadows, in selection order.
#[cfg(any(test, feature = "dump"))]
pub(crate) fn shadowed(selected: &[String], namespace: &str, minor: PyMinor) -> Vec<Shadowed> {
    shadowed_in(selected, namespace, &[], minor)
}

pub(crate) fn shadowed_in(
    selected: &[String],
    namespace: &str,
    roots: &[String],
    minor: PyMinor,
) -> Vec<Shadowed> {
    let named: Vec<(&String, String)> = selected
        .iter()
        .filter_map(|rel| scoped(rel, namespace, roots, minor).map(|module| (rel, module)))
        .collect();
    let packages: HashSet<&str> = named
        .iter()
        .filter_map(|(rel, _)| rel.strip_suffix("/__init__.py"))
        .collect();
    named
        .iter()
        .filter(|(rel, _)| {
            !is_package(rel)
                && rel
                    .strip_suffix(".py")
                    .is_some_and(|path| packages.contains(path))
        })
        .map(|(rel, module)| Shadowed {
            file: (*rel).clone(),
            module: module.clone(),
        })
        .collect()
}

fn is_package(rel: &str) -> bool {
    rel.rsplit('/').next() == Some("__init__.py")
}

#[cfg(test)]
#[path = "names_tests.rs"]
mod tests;
