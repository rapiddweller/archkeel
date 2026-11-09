// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Paths relative to the snapshot, written with `/`.

/// The directory of a path: `a/b.rs` gives `a`, and `b.rs` gives the empty text.
pub fn dirname(path: &str) -> &str {
    path.rsplit_once('/').map_or("", |(dir, _)| dir)
}

/// `dir/rel`; the empty directory is the snapshot root.
pub fn join(dir: &str, rel: &str) -> String {
    if dir.is_empty() || dir == "." {
        rel.to_owned()
    } else {
        format!("{dir}/{rel}")
    }
}

/// Remove `.` and `..` parts. `None` when the path leaves the snapshot or is not relative.
pub fn normalize(path: &str) -> Option<String> {
    if path.starts_with('/') || path.contains('\\') || path.contains('\0') {
        return None;
    }
    let mut parts: Vec<&str> = Vec::new();
    for part in path.split('/') {
        match part {
            "" | "." => {}
            ".." => {
                parts.pop()?;
            }
            other => parts.push(other),
        }
    }
    (!parts.is_empty()).then(|| parts.join("/"))
}

#[cfg(test)]
#[path = "paths_tests.rs"]
mod tests;
