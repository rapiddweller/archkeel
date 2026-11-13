// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Test scope of a 9.0.0 request (AD-313, AD-335).
//!
//! The collector owns the `cfg(test)` rule (`attrs.rs`, `tree.rs`). This module holds the path
//! check that the host also applies: the host refuses a reply that selects a file in a test
//! directory, so the collector must treat each such file as test scope.

/// `explore_scope.NO_PRODUCTION_SOURCE`: the exclusion removed every file, so the scan is not complete.
pub(crate) const NO_PRODUCTION_SOURCE: &str =
    "No production source files in scope after the test exclusion";

/// `profiles.is_test_source(path, Language.RUST)`: a directory of test, bench or example code.
const TEST_DIRECTORIES: [&str; 5] = ["test", "tests", "__tests__", "benches", "examples"];

/// Whether a directory of `rel` is a test directory.
pub(crate) fn in_test_directory(rel: &str) -> bool {
    let mut parts = rel
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".");
    let _file = parts.next_back();
    parts.any(|part| TEST_DIRECTORIES.contains(&part))
}

#[cfg(test)]
#[path = "test_scope_tests.rs"]
mod tests;
