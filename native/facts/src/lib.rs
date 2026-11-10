// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The one typed definition of each collector fact that crosses the process boundary (AD-345).
//!
//! A collector builds these types, and the same types give two JSON forms:
//!
//! 1. The protocol 9 wire (`serde::Serialize`). It is byte-equal to the reply that the collectors
//!    write today, so a collector can adopt the types without a change of the wire.
//! 2. The read-set (`readset::ReadSet`). It holds only the fields that a rule or a view reads
//!    (WP1 of issue #880). It is the form of the seam to the Python shell.
//!
//! `schema::schema` generates the JSON schema of the wire from the types. The committed schema
//! never changes: a change of a type that changes the schema fails `schema_tests`.
//!
//! The vocabularies are closed enums. A value that the protocol does not know is an error, not a
//! string. A source id never converts to a Target id (`ids`).

#[macro_use]
mod macros;

pub mod data;
pub mod ids;
pub mod nested;
pub mod nullable;
pub mod producer;
pub mod readset;
pub mod reason;
pub mod record;
pub mod schema;
pub mod sections;
pub mod vocab;

pub use record::{FactData, Record};
pub use sections::{
    BindingFact, CallFact, ConstructFact, GapFact, ImportFact, ReferenceFact, Section, SignalFact,
    SymbolFact,
};
