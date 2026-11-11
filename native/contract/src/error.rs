// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed error kinds of the contract parser.
//!
//! The first three kinds are the three error classes of the Python parser (`ir/codec_contract.py`):
//! `ValueError`, `ContractVersionError` and `ContractInputError`. `DuplicateKey` is stricter than
//! Python, which keeps the last value of a repeated key. `Unsupported` names a part of the grammar
//! that this crate does not parse yet: the parser stops there and never skips the part.

use std::fmt;

use crate::model::RuleKind;

/// A part of the contract grammar that slice 0c-2 of epic #880 ports.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Unported {
    /// The `declarations` object of the root (capabilities, budgets, paths, modules, UML).
    Declarations,
    /// A rule kind that only the Python profile decides.
    Rule(RuleKind),
}

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
    /// The contract uses a part of the grammar that this crate does not parse yet.
    Unsupported(Unported),
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

pub(crate) fn unsupported(part: Unported, message: impl Into<String>) -> ParseError {
    ParseError {
        kind: ErrorKind::Unsupported(part),
        message: message.into(),
    }
}

pub(crate) type Parsed<T> = Result<T, ParseError>;
