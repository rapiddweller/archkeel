// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The selected files of a scan, as `explore_scope.selected_paths` finds them.
//!
//! `Path.rglob("*.py")` yields each entry whose name ends with `.py`, a directory too, and enters
//! each directory that is not a symlink. A file under `__pycache__`, a file that resolves outside
//! the snapshot and, when the scope leaves tests out, a test source (as written or as resolved)
//! is not selected. The order is the order of the path parts.

use archkeel_snapshot::paths::join;
use archkeel_snapshot::Snapshot;

/// The selected snapshot paths of the roots, sorted by their parts.
pub fn selected(snapshot: &mut Snapshot, roots: &[String], exclude_tests: bool) -> Vec<String> {
    let mut found = Vec::new();
    for root in roots {
        if !snapshot.is_dir(root) {
            continue;
        }
        let mut pending = vec![root.trim_end_matches('/').to_owned()];
        while let Some(directory) = pending.pop() {
            let (files, directories) = snapshot.entries(&directory);
            let names = files.iter().chain(directories.iter());
            found.extend(
                names
                    .filter(|name| name.ends_with(".py"))
                    .map(|name| join(&directory, name)),
            );
            let children = directories.iter().map(|name| join(&directory, name));
            pending.extend(children.filter(|child| !snapshot.is_link(child)));
        }
    }
    found.retain(|rel| keep(snapshot, rel, exclude_tests));
    found.sort_by(|left, right| left.split('/').cmp(right.split('/')));
    found.dedup();
    found
}

fn keep(snapshot: &mut Snapshot, rel: &str, exclude_tests: bool) -> bool {
    if rel.split('/').any(|part| part == "__pycache__") {
        return false;
    }
    let Some(real) = snapshot.real(rel) else {
        return false;
    };
    !(exclude_tests && (is_test_source(rel) || is_test_source(&real)))
}

/// `profiles.is_test_source` for Python: a part `test`, `tests` or `__tests__` above the file, or
/// a name `test_*.py` or `*_test.py`.
pub fn is_test_source(path: &str) -> bool {
    let mut parts = path
        .rsplit('/')
        .filter(|part| !part.is_empty() && *part != ".");
    let name = parts.next().unwrap_or_default();
    let test_name =
        (name.starts_with("test_") && name.ends_with(".py")) || name.ends_with("_test.py");
    test_name || parts.any(|part| ["test", "tests", "__tests__"].contains(&part))
}

#[cfg(test)]
#[path = "discover_tests.rs"]
mod tests;
