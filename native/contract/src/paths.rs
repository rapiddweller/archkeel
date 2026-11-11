// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The repository path checks of `ir/contract_paths.py`, without file system access.

/// `contract_relative_path(value) is not None`: not absolute, no `..` segment and no backslash.
fn relative(value: &str) -> bool {
    !value.starts_with('/') && !value.contains('\\') && !value.split('/').any(|part| part == "..")
}

/// `str(PurePosixPath(value)) == value` for a relative path: no empty or `.` segment, and `.`
/// for an empty path.
fn normal(value: &str) -> bool {
    let parts: Vec<&str> = value
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect();
    let joined = if parts.is_empty() {
        ".".to_owned()
    } else {
        parts.join("/")
    };
    joined == value
}

/// A file path of a module entity: relative and written in its normal form.
pub(crate) fn normal_relative_path(value: &str) -> bool {
    relative(value) && normal(value)
}

/// `PurePosixPath(value).suffix`.
fn suffix(value: &str) -> &str {
    let name = value.rsplit('/').next().unwrap_or(value);
    match name.rfind('.') {
        Some(index) if index > 0 && index + 1 < name.len() => &name[index..],
        _ => "",
    }
}

const SOURCE_SUFFIXES: [&str; 10] = [
    ".py", ".dart", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs",
];

/// `validate_module_target_path`: a repository-relative source path.
pub(crate) fn module_target_path(value: &str) -> bool {
    let drive = value.len() >= 2
        && value.as_bytes()[0].is_ascii_alphabetic()
        && value.as_bytes()[1] == b':';
    !value.is_empty()
        && normal_relative_path(value)
        && !drive
        && !value.contains('\0')
        && SOURCE_SUFFIXES.contains(&suffix(value))
}
