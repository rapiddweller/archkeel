// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Python files outside the scan roots that are test source (#2240).
//!
//! A file counts as test source when `is_test_source` says so, when it is named `conftest.py`, or
//! when it lies under a literal path of `testpaths` in the pytest configuration of the root. Test
//! source is no product runtime: the walk of `outside.rs` does not read it, as it does not read a
//! file under `tests/`. A `conftest.py` or a test path inside a scan root is not touched here: the
//! scan reads it as product code.
//!
//! The configuration file is chosen as pytest chooses it: `pytest.ini`, then `pyproject.toml` with
//! `[tool.pytest.ini_options]`, then `tox.ini` with `[pytest]`, then `setup.cfg` with
//! `[tool:pytest]`. A glob entry, an absolute entry and an entry with `..` name no path here, so a
//! file is never left out on a guess.

use archkeel_snapshot::Snapshot;

use crate::discover::is_test_source;
use crate::requirement::pytest_testpaths;

const CONFTEST: &str = "conftest.py";
const INI_FILES: [(&str, &str); 3] = [
    ("pytest.ini", "pytest"),
    ("tox.ini", "pytest"),
    ("setup.cfg", "tool:pytest"),
];

/// The literal `testpaths` entries of the root, as relative paths without a trailing slash.
pub(super) fn testpaths(snapshot: &mut Snapshot) -> Vec<String> {
    let text = |snapshot: &mut Snapshot, name: &str| {
        snapshot
            .read(name)
            .and_then(|raw| String::from_utf8(raw).ok())
    };
    if let Some(ini) = text(snapshot, "pytest.ini") {
        return literal(&ini_value(&ini, "pytest"));
    }
    if let Some(entries) = pytest_testpaths(snapshot) {
        return literal(&entries);
    }
    for (name, section) in &INI_FILES[1..] {
        if let Some(ini) = text(snapshot, name) {
            if has_section(&ini, section) {
                return literal(&ini_value(&ini, section));
            }
        }
    }
    Vec::new()
}

/// True when `rel` is test source for the walk outside the scan roots.
pub(super) fn is_outside_test_source(rel: &str, testpaths: &[String]) -> bool {
    let name = rel.rsplit('/').next().unwrap_or_default();
    is_test_source(rel)
        || name == CONFTEST
        || testpaths
            .iter()
            .any(|path| rel == path || rel.starts_with(&format!("{path}/")))
}

fn has_section(text: &str, section: &str) -> bool {
    text.lines()
        .any(|line| line.trim() == format!("[{section}]"))
}

/// The words of the `testpaths` key in one section of an ini file. A continuation line starts with
/// a space or a tab.
fn ini_value(text: &str, section: &str) -> Vec<String> {
    let mut inside = false;
    let mut collecting = false;
    let mut words = Vec::new();
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            inside = trimmed == format!("[{section}]");
            collecting = false;
            continue;
        }
        if !inside || trimmed.starts_with('#') || trimmed.starts_with(';') {
            continue;
        }
        let continued = line.starts_with([' ', '\t']) && collecting;
        if continued {
            words.extend(trimmed.split_whitespace().map(str::to_owned));
        } else if let Some((key, value)) = trimmed.split_once(['=', ':']) {
            collecting = key.trim() == "testpaths";
            if collecting {
                words.extend(value.split_whitespace().map(str::to_owned));
            }
        } else {
            collecting = false;
        }
    }
    words
}

fn literal(entries: &[String]) -> Vec<String> {
    entries
        .iter()
        .filter(|entry| !entry.contains(['*', '?', '[']))
        .filter(|entry| !entry.starts_with('/') && !entry.split('/').any(|part| part == ".."))
        .map(|entry| {
            let kept = entry.strip_prefix("./").unwrap_or(entry);
            kept.trim_end_matches('/').to_owned()
        })
        .filter(|entry| !entry.is_empty() && entry != ".")
        .collect()
}

#[cfg(test)]
#[path = "outside_testpaths_tests.rs"]
mod tests;
