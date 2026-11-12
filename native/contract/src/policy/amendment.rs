// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Read and write an amendment of schema 2.0.0, as Python `parse_amendment` and `amendment_bytes`
//! (`ir/amendment_codec.py`) do. An amendment is the record of a person who decided to widen the
//! contract from one exact comparison to another (AD-61). This module does not decide whether an
//! amendment covers a change: `policy::bind` does.
//!
//! Rust is stricter than Python in three cases (AD-375): it refuses schema 1.0.0, a JSON object
//! with one key two times, and a lone surrogate escape.

use std::fmt;

use crate::canonical::write_text;
use crate::json::{self, field, keys, Json, Object};
use crate::policy::reference::python_repr;

/// The only schema version that this module reads and writes.
pub const AMENDMENT_VERSION: &str = "2.0.0";

text_type!(
    pub(crate),
    /// A lowercase SHA-256 digest in hex, as Python `_amendment_digest` accepts it.
    AmendmentDigest
);

record!(
    pub(crate),
    /// A checked amendment of schema 2.0.0. Only `parse_amendment` and `Binding::amend` make one.
    Amendment {
        before_digest: AmendmentDigest,
        after_digest: AmendmentDigest,
        decided_by: String,
        rationale: String,
        before_baseline_digest: Option<AmendmentDigest>,
        after_baseline_digest: Option<AmendmentDigest>,
    }
);

/// One field of an amendment. Its key is the JSON key.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AmendmentField {
    BeforeDigest,
    AfterDigest,
    DecidedBy,
    Rationale,
    BeforeBaselineDigest,
    AfterBaselineDigest,
}

impl AmendmentField {
    /// The JSON key of the field.
    pub fn key(self) -> &'static str {
        match self {
            AmendmentField::BeforeDigest => "before_digest",
            AmendmentField::AfterDigest => "after_digest",
            AmendmentField::DecidedBy => "decided_by",
            AmendmentField::Rationale => "rationale",
            AmendmentField::BeforeBaselineDigest => "before_baseline_digest",
            AmendmentField::AfterBaselineDigest => "after_baseline_digest",
        }
    }
}

/// Why bytes are not an amendment. Each kind except `Json`, `DuplicateKey`, `Version1` and
/// `UnsupportedSchema` of a value that is not a text, `null`, a boolean or an integer has the
/// message of Python.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum AmendmentError {
    /// Invalid UTF-8, invalid JSON, a lone surrogate escape or nesting deeper than 128 levels.
    Json(String),
    /// One JSON object holds one key two times. Python keeps the last value.
    DuplicateKey(String),
    /// The document is not a JSON object.
    NotObject,
    /// The schema version is not a known amendment schema. The text is the Python `repr` of the
    /// value.
    UnsupportedSchema(String),
    /// Schema 1.0.0, which binds no baseline. Python reads it; Rust does not (AD-375).
    Version1,
    /// The keys are not the keys of schema 2.0.0.
    FieldsMismatch,
    /// The field is not a JSON text.
    NotString(AmendmentField),
    /// The field is not a lowercase SHA-256 digest.
    NotDigest(AmendmentField),
    /// The field is empty or holds only white space.
    Empty(AmendmentField),
}

impl fmt::Display for AmendmentError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AmendmentError::Json(text) | AmendmentError::DuplicateKey(text) => {
                formatter.write_str(text)
            }
            AmendmentError::NotObject => formatter.write_str("amendment must be an object"),
            AmendmentError::UnsupportedSchema(text) => {
                write!(formatter, "unsupported amendment schema {text}")
            }
            AmendmentError::Version1 => formatter
                .write_str("amendment schema '1.0.0' binds no baseline; write the amendment again"),
            AmendmentError::FieldsMismatch => formatter.write_str("amendment fields mismatch"),
            AmendmentError::NotString(item) => {
                write!(formatter, "amendment.{} must be a string", item.key())
            }
            AmendmentError::NotDigest(item) => write!(
                formatter,
                "amendment.{} must be a lowercase SHA-256 digest",
                item.key()
            ),
            AmendmentError::Empty(item) => {
                write!(formatter, "amendment.{} must not be empty", item.key())
            }
        }
    }
}

impl std::error::Error for AmendmentError {}

/// The keys of schema 2.0.0.
const KEYS: [&str; 7] = [
    "schema_version",
    "before_digest",
    "after_digest",
    "decided_by",
    "rationale",
    "before_baseline_digest",
    "after_baseline_digest",
];

/// The characters of Python `str.isspace` (bidirectional class WS, B or S, or category Zs). Rust
/// `char::is_whitespace` does not hold U+001C to U+001F, so the table is written out.
const PYTHON_SPACE: [char; 29] = [
    '\t', '\n', '\u{b}', '\u{c}', '\r', '\u{1c}', '\u{1d}', '\u{1e}', '\u{1f}', ' ', '\u{85}',
    '\u{a0}', '\u{1680}', '\u{2000}', '\u{2001}', '\u{2002}', '\u{2003}', '\u{2004}', '\u{2005}',
    '\u{2006}', '\u{2007}', '\u{2008}', '\u{2009}', '\u{200a}', '\u{2028}', '\u{2029}', '\u{202f}',
    '\u{205f}', '\u{3000}',
];

/// Python `value.strip() == ""`.
pub(crate) fn blank(value: &str) -> bool {
    value.chars().all(|item| PYTHON_SPACE.contains(&item))
}

/// Python `re.fullmatch("[0-9a-f]{64}", value)`.
fn digest_text(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|item| item.is_ascii_digit() || (b'a'..=b'f').contains(&item))
}

/// A digest that this crate computed: always 64 lowercase hex digits.
pub(crate) fn computed_digest(value: &str) -> AmendmentDigest {
    AmendmentDigest(value.to_owned())
}

/// Read amendment bytes in the order of the checks of Python `parse_amendment`.
pub fn parse_amendment(bytes: &[u8]) -> Result<Amendment, AmendmentError> {
    let value = json::read(bytes).map_err(|error| match error.kind {
        crate::ErrorKind::DuplicateKey => AmendmentError::DuplicateKey(error.message),
        _ => AmendmentError::Json(error.message),
    })?;
    let Json::Object(document) = value else {
        return Err(AmendmentError::NotObject);
    };
    match field(&document, "schema_version") {
        Some(Json::Text(text)) if text == AMENDMENT_VERSION => {}
        Some(Json::Text(text)) if text == "1.0.0" => return Err(AmendmentError::Version1),
        other => return Err(AmendmentError::UnsupportedSchema(schema_repr(other))),
    }
    let mut seen: Vec<&str> = keys(&document).collect();
    seen.sort_unstable();
    let mut wanted = KEYS.to_vec();
    wanted.sort_unstable();
    if seen != wanted {
        return Err(AmendmentError::FieldsMismatch);
    }
    Ok(Amendment {
        before_digest: digest(&document, AmendmentField::BeforeDigest)?,
        after_digest: digest(&document, AmendmentField::AfterDigest)?,
        decided_by: nonempty(&document, AmendmentField::DecidedBy)?,
        rationale: nonempty(&document, AmendmentField::Rationale)?,
        before_baseline_digest: optional_digest(&document, AmendmentField::BeforeBaselineDigest)?,
        after_baseline_digest: optional_digest(&document, AmendmentField::AfterBaselineDigest)?,
    })
}

/// The Python `repr` of a schema version that is not known; `None` when the key is absent.
fn schema_repr(value: Option<&Json>) -> String {
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

fn text(document: &Object, item: AmendmentField) -> Result<&str, AmendmentError> {
    match field(document, item.key()) {
        Some(Json::Text(value)) => Ok(value),
        _ => Err(AmendmentError::NotString(item)),
    }
}

fn digest(document: &Object, item: AmendmentField) -> Result<AmendmentDigest, AmendmentError> {
    let value = text(document, item)?;
    if digest_text(value) {
        Ok(AmendmentDigest(value.to_owned()))
    } else {
        Err(AmendmentError::NotDigest(item))
    }
}

fn optional_digest(
    document: &Object,
    item: AmendmentField,
) -> Result<Option<AmendmentDigest>, AmendmentError> {
    match field(document, item.key()) {
        Some(Json::Null) => Ok(None),
        _ => digest(document, item).map(Some),
    }
}

pub(crate) fn nonempty_text(value: &str, item: AmendmentField) -> Result<String, AmendmentError> {
    if blank(value) {
        Err(AmendmentError::Empty(item))
    } else {
        Ok(value.to_owned())
    }
}

fn nonempty(document: &Object, item: AmendmentField) -> Result<String, AmendmentError> {
    nonempty_text(text(document, item)?, item)
}

/// The bytes of Python `amendment_bytes`: `json.dumps(sort_keys=True, indent=2,
/// ensure_ascii=False)` and a line feed, in UTF-8.
pub fn amendment_bytes(amendment: &Amendment) -> Vec<u8> {
    let optional = |value: &Option<AmendmentDigest>| {
        value
            .as_ref()
            .map_or_else(|| "null".to_owned(), |item| quoted(item.as_text()))
    };
    let entries = [
        (
            "after_baseline_digest",
            optional(&amendment.after_baseline_digest),
        ),
        ("after_digest", quoted(amendment.after_digest.as_text())),
        (
            "before_baseline_digest",
            optional(&amendment.before_baseline_digest),
        ),
        ("before_digest", quoted(amendment.before_digest.as_text())),
        ("decided_by", quoted(&amendment.decided_by)),
        ("rationale", quoted(&amendment.rationale)),
        ("schema_version", quoted(AMENDMENT_VERSION)),
    ];
    let body: Vec<String> = entries
        .iter()
        .map(|(key, value)| format!("  \"{key}\": {value}"))
        .collect();
    format!("{{\n{}\n}}\n", body.join(",\n")).into_bytes()
}

/// A JSON text as Python `json.dumps(..., ensure_ascii=False)` writes it.
fn quoted(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 2);
    write_text(&mut out, value);
    out
}
