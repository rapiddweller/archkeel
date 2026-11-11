// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The path rules of an inside reference, equal to Python `contract_relative_path`,
//! `_safe_inside_reference` and `_contract_identity` (`ir/codec_inside.py`). They read no file.

/// The parts of a relative POSIX path, as Python `PurePosixPath(value).parts` gives them: no empty
/// part and no `.` part.
fn parts(value: &str) -> Vec<&str> {
    value
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect()
}

/// Python `contract_relative_path(value) is not None`: not absolute, no backslash, no `..` part.
fn relative(value: &str) -> bool {
    !value.starts_with('/') && !value.contains('\\') && !value.split('/').any(|part| part == "..")
}

/// The repository path that a reference names, or `None` when it names no file. Python
/// `_contract_identity`.
pub(crate) fn identity(value: &str) -> Option<String> {
    let parts = parts(value);
    (relative(value) && !parts.is_empty()).then(|| parts.join("/"))
}

/// Python `_safe_inside_reference`: a reference that a mount can read. Its test for `""`, `.` and
/// `..` is not here: `identity` refuses each of them.
pub(crate) fn safe(value: &str) -> bool {
    identity(value).is_some() && !value.contains(['\0', ':'])
}

/// A text as Python `repr` writes it, for the texts of a reason.
pub(crate) fn python_repr(value: &str) -> String {
    let quote = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let body: String = value.chars().map(|item| escaped(item, quote)).collect();
    format!("{quote}{body}{quote}")
}

/// One character of a Python `repr`.
fn escaped(character: char, quote: char) -> String {
    let code = u32::from(character);
    match character {
        '\\' => "\\\\".to_owned(),
        '\t' => "\\t".to_owned(),
        '\n' => "\\n".to_owned(),
        '\r' => "\\r".to_owned(),
        _ if character == quote => format!("\\{character}"),
        _ if code < 0x20 || (0x7f..0xa1).contains(&code) => format!("\\x{code:02x}"),
        _ => character.to_string(),
    }
}
