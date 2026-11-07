// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! POSIX path text and TypeScript file suffixes, as `config.py` and `source_input.py` read them.

/// `posixpath.normpath`.
pub fn normpath(path: &str) -> String {
    if path.is_empty() {
        return ".".to_owned();
    }
    let leading = if path.starts_with("//") && !path.starts_with("///") {
        "//"
    } else if path.starts_with('/') {
        "/"
    } else {
        ""
    };
    let mut parts: Vec<&str> = Vec::new();
    for part in path.split('/') {
        match part {
            "" | "." => {}
            ".." if leading.is_empty() && parts.last().is_none_or(|last| *last == "..") => {
                parts.push("..");
            }
            ".." => {
                parts.pop();
            }
            _ => parts.push(part),
        }
    }
    let joined = format!("{leading}{}", parts.join("/"));
    if joined.is_empty() {
        ".".to_owned()
    } else {
        joined
    }
}

/// `config.join`: `posixpath.join`, then `normpath`.
pub fn join(base: &str, path: &str) -> String {
    if path.starts_with('/') || base.is_empty() {
        normpath(path)
    } else if base.ends_with('/') {
        normpath(&format!("{base}{path}"))
    } else {
        normpath(&format!("{base}/{path}"))
    }
}

/// `posixpath.dirname`.
pub fn dirname(path: &str) -> &str {
    match path.rfind('/') {
        None => "",
        Some(index) => {
            let head = &path[..=index];
            let trimmed = head.trim_end_matches('/');
            if trimmed.is_empty() {
                head
            } else {
                trimmed
            }
        }
    }
}

/// `posixpath.basename`.
pub fn basename(path: &str) -> &str {
    path.rsplit('/').next().unwrap_or(path)
}

/// `config.is_outside`: the path names the parent directory.
pub fn is_outside(path: &str) -> bool {
    path == ".." || path.starts_with("../")
}

/// `config.within`.
pub fn within(scope: &str, path: &str) -> bool {
    scope == "." || path == scope || path.starts_with(&format!("{scope}/"))
}

/// The kind of source a recognized file suffix holds.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SourceKind {
    TypeScript,
    Declaration,
    JavaScript,
}

// Longest suffix first; `.json` is recognized but holds no source.
const SUFFIXES: [(&str, Option<SourceKind>); 12] = [
    (".d.mts", Some(SourceKind::Declaration)),
    (".d.cts", Some(SourceKind::Declaration)),
    (".d.ts", Some(SourceKind::Declaration)),
    (".json", None),
    (".mjs", Some(SourceKind::JavaScript)),
    (".mts", Some(SourceKind::TypeScript)),
    (".cjs", Some(SourceKind::JavaScript)),
    (".cts", Some(SourceKind::TypeScript)),
    (".tsx", Some(SourceKind::TypeScript)),
    (".jsx", Some(SourceKind::JavaScript)),
    (".ts", Some(SourceKind::TypeScript)),
    (".js", Some(SourceKind::JavaScript)),
];
const PLAIN: [&str; 5] = [".ts", ".tsx", ".d.ts", ".js", ".jsx"];
const ESM: [&str; 3] = [".mts", ".d.mts", ".mjs"];
const CJS: [&str; 3] = [".cts", ".d.cts", ".cjs"];

/// The longest recognized suffix of `name` and the source kind it holds.
pub fn suffix(name: &str) -> Option<(&'static str, Option<SourceKind>)> {
    SUFFIXES
        .iter()
        .copied()
        .find(|(suffix, _)| name.ends_with(suffix))
}

/// Whether `name` is a JSON file name.
pub fn is_json(name: &str) -> bool {
    suffix(name).is_some_and(|(found, _)| found == ".json")
}

/// `config._shadowed`: a sibling with the same stem and a higher-priority suffix wins.
pub fn shadowed(path: &str, known: &dyn Fn(&str) -> bool) -> bool {
    let Some((found, _)) = suffix(path) else {
        return false;
    };
    let stem = &path[..path.len() - found.len()];
    let group: &[&str] = if PLAIN.contains(&found) {
        &PLAIN
    } else if ESM.contains(&found) {
        &ESM
    } else if CJS.contains(&found) {
        &CJS
    } else {
        return false;
    };
    let position = group.iter().position(|item| *item == found).unwrap_or(0);
    group[..position].iter().any(|better| {
        known(&format!("{stem}{better}"))
            && !(*better == ".d.ts" && matches!(found, ".js" | ".jsx"))
    })
}

#[cfg(test)]
#[path = "paths_tests.rs"]
mod tests;
