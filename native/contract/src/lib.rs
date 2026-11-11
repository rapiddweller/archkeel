// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-contract, slices 0c-1 and 0c-2 of WP6 (AD-359, epic #880).
//!
//! The crate parses the bytes of one architecture contract into typed and closed structures. It
//! accepts and rejects what the Python parser (`ir/codec_contract.py`) accepts and rejects, with
//! the same error kind, and writes the same canonical bytes. It reads no file: the shell sends the
//! bytes. It evaluates nothing, and it does not depend on `archkeel-facts`, so a Target id can
//! never be a source id.
//!
//! It covers the whole grammar of `parse_contract`: components, the 22 rule kinds and the
//! `declarations` object with its UML Target and the checks of `declared_graph`.

#![deny(unreachable_pub)]

#[macro_use]
mod macros;
mod boundary;
mod budgets;
mod canonical;
mod component;
mod construct;
mod contract;
mod declarations;
mod dependency;
mod document;
mod error;
mod graph;
mod graph_check;
mod graph_link;
mod json;
mod model;
mod model_declarations;
mod model_rules;
mod model_uml;
mod names;
mod paths;
mod python_rules;
mod read;
mod rule;
mod rules;
mod structure;
mod uml;
mod version;
mod words;

pub use canonical::{canonical_bytes, canonical_digest};
pub use contract::parse;
pub use document::{Contract, InsideRef, NeedsTree, ParsedContract};
pub use error::{ErrorKind, ParseError};
pub use model::*;
pub use model_declarations::*;
pub use model_rules::*;
pub use model_uml::*;
pub use rule::{head_of, kind_of, Rule};
pub use version::{version_text, ContractVersion};
