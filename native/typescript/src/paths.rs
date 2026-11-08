// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! POSIX path text, as `config.py` reads it.

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

#[cfg(test)]
#[path = "paths_tests.rs"]
mod tests;
