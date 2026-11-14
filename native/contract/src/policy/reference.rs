// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The path rules of an inside reference, equal to Python `contract_relative_path`,
//! `_safe_inside_reference` and `_contract_identity` (`ir/codec_inside.py`). They read no file.

use crate::policy::printable::NOT_PRINTABLE;

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
    (relative(value) && !value.contains('\0') && !parts.is_empty()).then(|| parts.join("/"))
}

/// Python `_safe_inside_reference`: a reference that a mount can read. Its test for `""`, `.` and
/// `..` is not here: `identity` refuses each of them.
pub(crate) fn safe(value: &str) -> bool {
    identity(value).is_some() && !value.contains(':')
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

/// Python `str.isprintable` for one character, from the table of Python 3.11 (L-28).
pub(crate) fn printable(character: char) -> bool {
    let code = u32::from(character);
    NOT_PRINTABLE
        .binary_search_by(|(start, end)| {
            if code < *start {
                std::cmp::Ordering::Greater
            } else if code > *end {
                std::cmp::Ordering::Less
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_err()
}

/// One character of a Python `repr`: `\xNN`, `\uNNNN` or `\UNNNNNNNN` when it is not printable.
fn escaped(character: char, quote: char) -> String {
    let code = u32::from(character);
    match character {
        '\\' => "\\\\".to_owned(),
        '\t' => "\\t".to_owned(),
        '\n' => "\\n".to_owned(),
        '\r' => "\\r".to_owned(),
        _ if character == quote => format!("\\{character}"),
        _ if printable(character) => character.to_string(),
        _ if code < 0x100 => format!("\\x{code:02x}"),
        _ if code < 0x1_0000 => format!("\\u{code:04x}"),
        _ => format!("\\U{code:08x}"),
    }
}
