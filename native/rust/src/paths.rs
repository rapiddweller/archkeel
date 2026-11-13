// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The one path rule that is specific to Rust: the file of a `mod` or of a `#[path]`.

use archkeel_snapshot::paths::{is_outside, normpath};

/// Remove `.` and `..` parts. `None` when the path leaves the snapshot or is not relative.
pub(crate) fn normalize(path: &str) -> Option<String> {
    if path.starts_with('/') || path.contains('\\') || path.contains('\0') {
        return None;
    }
    let normal = normpath(path);
    (normal != "." && !is_outside(&normal)).then_some(normal)
}

#[cfg(test)]
#[path = "paths_tests.rs"]
mod tests;
