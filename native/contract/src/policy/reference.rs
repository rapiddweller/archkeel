// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The path rules of an inside reference. They read no file.

use crate::json::Json;
use crate::policy::printable::NOT_PRINTABLE;

/// The parts of a relative POSIX path, as Python `PurePosixPath(value).parts` gives them: no empty
/// part and no `.` part.
fn parts(value: &str) -> Vec<&str> {
    value
        .split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect()
}

/// A safe reference is not absolute and has no backslash or `..` part.
fn relative(value: &str) -> bool {
    !value.starts_with('/') && !value.contains('\\') && !value.split('/').any(|part| part == "..")
}

/// The repository path that a reference names, or `None` when it names no file.
pub(crate) fn identity(value: &str) -> Option<String> {
    let parts = parts(value);
    (relative(value) && !value.contains('\0') && !parts.is_empty()).then(|| parts.join("/"))
}

/// A reference that a mount can read: its text is its identity. `./deep.json`, `a//deep.json`,
/// `a/./deep.json` and `deep.json/` name the file of `deep.json`, but they are another text, so a
/// mount with one of them is refused (#1067). A reference with a `:` is refused too. `identity`
/// itself refuses `""`, `.` and `..`.
pub(crate) fn safe(value: &str) -> bool {
    identity(value).as_deref() == Some(value) && !value.contains(':')
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

/// The Python `repr` of a schema version that is not known; `None` when the key is absent.
pub(super) fn schema_repr(value: Option<&Json>) -> String {
    match value {
        None | Some(Json::Null) => "None".to_owned(),
        Some(Json::Text(text)) => python_repr(text),
        Some(Json::Bool(true)) => "True".to_owned(),
        Some(Json::Bool(false)) => "False".to_owned(),
        Some(Json::Int(number)) => number.to_string(),
        Some(Json::Float) => "<float>".to_owned(),
        Some(Json::Array(_)) => "<list>".to_owned(),
        Some(Json::Object(_)) => "<dict>".to_owned(),
    }
}
