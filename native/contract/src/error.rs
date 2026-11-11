// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed error kinds of the contract parser.
//!
//! The first three kinds are the three error classes of the Python parser (`ir/codec_contract.py`):
//! `ValueError`, `ContractVersionError` and `ContractInputError`. `DuplicateKey` is stricter than
//! Python, which keeps the last value of a repeated key.

use std::fmt;

/// The kind of a parse error.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ErrorKind {
    /// The bytes are not a valid contract (Python `ValueError`).
    Invalid,
    /// The schema version is not a known contract version (Python `ContractVersionError`).
    Version,
    /// A component label repeats or a `requires` entry names no label (Python
    /// `ContractInputError`).
    Input,
    /// One JSON object holds one key two times.
    DuplicateKey,
}

/// A parse error: its kind and a message for a person.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParseError {
    pub kind: ErrorKind,
    pub message: String,
}

impl fmt::Display for ParseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for ParseError {}

pub(crate) fn invalid(message: impl Into<String>) -> ParseError {
    ParseError {
        kind: ErrorKind::Invalid,
        message: message.into(),
    }
}

pub(crate) type Parsed<T> = Result<T, ParseError>;
