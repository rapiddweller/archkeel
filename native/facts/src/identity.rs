// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Source identities. Each function gives the same text as its Python twin in `archkeel.ir`.

use sha2::{Digest, Sha256};

/// One part of a `stable_id`, written as Python `str()` writes it.
#[derive(Clone, Copy, Debug)]
pub enum Part<'a> {
    /// A text part.
    Text(&'a str),
    /// A whole number part.
    Number(i64),
    /// A boolean part.
    Flag(bool),
    /// A part with no value.
    Nothing,
}

impl Part<'_> {
    fn write(&self, out: &mut String) {
        match self {
            Part::Text(text) => out.push_str(text),
            Part::Number(number) => out.push_str(&number.to_string()),
            Part::Flag(true) => out.push_str("True"),
            Part::Flag(false) => out.push_str("False"),
            Part::Nothing => out.push_str("None"),
        }
    }
}

/// `archkeel.ir.facts.stable_id`: the prefix and 16 hex digits of SHA-256 over the parts.
pub fn stable_id(prefix: &str, parts: &[Part<'_>]) -> String {
    let mut payload = String::new();
    for (index, part) in parts.iter().enumerate() {
        if index > 0 {
            payload.push('\u{1f}');
        }
        part.write(&mut payload);
    }
    let digest = sha256_hex(payload.as_bytes());
    format!("{prefix}-{}", &digest[..16])
}

/// `archkeel.ir.source_records.evidence_id`: the identity of one source location.
pub fn evidence_id(rel_path: &str, line: i64, end_line: i64, column: i64) -> String {
    stable_id(
        "EVD",
        &[
            Part::Text(rel_path),
            Part::Number(line),
            Part::Number(end_line),
            Part::Number(column),
        ],
    )
}

/// The SHA-256 digest of data that comes in parts, for a file that is not held in memory.
#[derive(Default)]
pub struct StreamDigest(Sha256);

impl StreamDigest {
    /// Add the next part of the data.
    pub fn update(&mut self, data: &[u8]) {
        self.0.update(data);
    }

    /// The lowercase hex digest of all parts, the same as `sha256_hex` of the joined data.
    pub fn hex(self) -> String {
        self.0
            .finalize()
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }
}

/// The lowercase hex SHA-256 digest of `data`.
pub fn sha256_hex(data: &[u8]) -> String {
    Sha256::digest(data)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// `_relative` of the Python decoder: whether a path stays inside the snapshot. It is not
/// absolute, has no `..` part, no backslash and no colon. It does not test for an empty path, a
/// `.` part or a NUL: the callers differ there (`module_identity`, the snapshot paths).
pub fn inside(path: &str) -> bool {
    !(path.starts_with('/')
        || path.split('/').any(|part| part == "..")
        || path.contains('\\')
        || path.contains(':'))
}

/// `archkeel.ir.identity.module_identity`: a collision-free module ID for a TypeScript path.
pub fn module_identity(namespace: &str, path: &str) -> Result<String, String> {
    let unsafe_path = path.is_empty()
        || path.contains('\\')
        || path.contains('\0')
        || path.starts_with('/')
        || path.split('/').any(|part| matches!(part, "" | "." | ".."));
    if unsafe_path {
        return Err("source path must be a safe repository-relative POSIX path".to_owned());
    }
    if namespace.is_empty() || !namespace.split('.').all(is_identifier) {
        return Err("namespace must be a dotted identifier".to_owned());
    }
    let mut identity = namespace.to_owned();
    for part in path.split('/') {
        identity.push('.');
        identity.push_str(&encoded_segment(part));
    }
    Ok(identity)
}

/// The package of a module: everything before the last dot.
pub fn package_of(module: &str) -> &str {
    module.rsplit_once('.').map_or("", |(package, _)| package)
}

fn encoded_segment(value: &str) -> String {
    let mut encoded = String::new();
    for character in value.chars() {
        if character.is_ascii_alphanumeric() {
            encoded.push(character);
        } else {
            encoded.push_str(&format!("_x{:x}_", u32::from(character)));
        }
    }
    if let Some(first) = encoded.chars().next().filter(char::is_ascii_digit) {
        encoded = format!("_x{:x}_{}", u32::from(first), &encoded[1..]);
    }
    encoded
}

/// A module identity with its real characters, for a person (#1617): `encoded_segment` writes each
/// character that is no ASCII letter or digit as `_x<hex>_`; only such an escape is read back, and
/// a character that is not printable stays escaped. The identity itself is never changed.
pub fn readable(text: &str) -> String {
    let mut shown = String::with_capacity(text.len());
    let mut rest = text;
    while let Some(start) = rest.find("_x") {
        shown.push_str(&rest[..start]);
        let after = &rest[start + 2..];
        let decoded = after.find('_').and_then(|end| {
            let digits = &after[..end];
            let valid = (1..=6).contains(&digits.len())
                && digits.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f'));
            let character = valid
                .then(|| {
                    u32::from_str_radix(digits, 16)
                        .ok()
                        .and_then(char::from_u32)
                })
                .flatten()
                .filter(|c| !c.is_control() && !c.is_ascii_alphanumeric());
            character.map(|c| (c, end))
        });
        if let Some((character, end)) = decoded {
            shown.push(character);
            rest = &after[end + 1..];
        } else {
            shown.push_str("_x");
            rest = after;
        }
    }
    shown.push_str(rest);
    shown
}

/// An ASCII identifier. The request decoder accepts only ASCII namespaces.
pub fn is_identifier(value: &str) -> bool {
    let mut characters = value.chars();
    characters
        .next()
        .is_some_and(|first| first == '_' || first.is_ascii_alphabetic())
        && characters.all(|next| next == '_' || next.is_ascii_alphanumeric())
}

#[cfg(test)]
#[path = "identity_tests.rs"]
mod tests;
