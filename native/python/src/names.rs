// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Module names as `source.module_for` and `source.package_for` give them, and the modules that a
//! package of the same name shadows (`explore_scope.parse_unshadowed`, #797).

use std::collections::HashSet;

use archkeel_facts::identity::{stable_id, Part};

/// The dotted module of a snapshot path: the path from the first part where the namespace
/// starts, without its last suffix and without a last `__init__`. `None` when the path does not
/// hold the namespace (`module_for` raises `ValueError`).
pub fn module_for(rel: &str, namespace: &str) -> Option<String> {
    let mut parts: Vec<&str> = rel.split('/').filter(|part| !part.is_empty()).collect();
    let last = parts.pop()?;
    parts.push(without_suffix(last));
    if parts.last() == Some(&"__init__") {
        parts.pop();
    }
    let prefix: Vec<&str> = namespace.split('.').collect();
    let start = parts
        .windows(prefix.len())
        .position(|window| window == prefix.as_slice())?;
    Some(parts[start..].join("."))
}

/// `PurePath.with_suffix("")`: a name drops its last suffix; a name that starts with its only dot
/// keeps it.
fn without_suffix(name: &str) -> &str {
    match name.rfind('.') {
        Some(at) if at > 0 && at + 1 < name.len() => &name[..at],
        _ => name,
    }
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
            python_repr(&self.module)
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

pub const SHADOWED_KIND: &str = "ShadowedModule";

/// The selected modules that a package of the same name shadows, in the order of `selected`.
pub fn shadowed(selected: &[String], namespace: &str) -> Vec<Shadowed> {
    let named: Vec<(&String, String)> = selected
        .iter()
        .filter_map(|rel| module_for(rel, namespace).map(|module| (rel, module)))
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

/// `repr()` of a Python `str`: single quotes unless the text holds one and no double quote.
fn python_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::from(quote);
    for character in text.chars() {
        match character {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            _ if character == quote => {
                out.push('\\');
                out.push(character);
            }
            _ if (character as u32) < 0x20 || character == '\u{7f}' => {
                out.push_str(&format!("\\x{:02x}", character as u32));
            }
            _ => out.push(character),
        }
    }
    out.push(quote);
    out
}

#[cfg(test)]
#[path = "names_tests.rs"]
mod tests;
