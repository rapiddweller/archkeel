// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Test-source exclusion of a 9.0.0 request (AD-313).
//!
//! A recognized test source leaves the scan. The host refuses a reply that selects one.

/// `explore_scope.NO_PRODUCTION_SOURCE`: the exclusion removed every file, so the scan is not complete.
pub const NO_PRODUCTION_SOURCE: &str =
    "No production source files in scope after the test exclusion";

/// `profiles.is_test_source(path, Language.TYPESCRIPT)`: a test directory or a test file name.
pub fn is_test_source(path: &str) -> bool {
    let parts: Vec<&str> = path
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect();
    let Some((name, directories)) = parts.split_last() else {
        return false;
    };
    if directories
        .iter()
        .any(|part| matches!(*part, "test" | "tests" | "__tests__"))
    {
        return true;
    }
    // `\.(?:test|spec)\.[^.]+$`: the name ends in `.test.<ext>` or `.spec.<ext>`.
    let Some((stem, extension)) = name.rsplit_once('.') else {
        return false;
    };
    !extension.is_empty() && (stem.ends_with(".test") || stem.ends_with(".spec"))
}

#[cfg(test)]
#[path = "test_sources_tests.rs"]
mod tests;
