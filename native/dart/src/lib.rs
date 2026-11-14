// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The native Dart collector of Archkeel as a library (#880, AD-454).
//!
//! `survey` gives the typed import survey of one request: the selected sources, the file facts,
//! the part owners, the import records with their targets and the named gaps. `typed_reply`
//! assembles it as a reply with the sections `imports` and `unknowns`. The binary
//! `archkeel-dart-collector` decodes a request and still writes no reply. `archkeel-collect`
//! links this crate and runs `typed_reply` in the process of the core (AD-468).

#![forbid(unsafe_code)]
#![deny(unreachable_pub)]
// The survey parses directives only. The full parse of definitions and sites serves the dump until a later slice of #880 surveys symbols; the expectation fails once it is used.
#![cfg_attr(
    not(feature = "dump"),
    expect(
        dead_code,
        reason = "the full parse serves the dump until a slice of #880 surveys symbols (AD-454)"
    )
)]

#[cfg(feature = "dump")]
mod collection;
mod dartstr;
#[cfg(feature = "dump")]
mod declarations;
mod definitions;
mod directives;
mod discover;
mod import_survey;
mod members;
mod module;
mod nesting;
mod parameters;
mod parse;
mod pubspec;
mod pytext;
mod records;
mod sdk;
mod sites;
mod syntax;
mod tree;
mod unicode_tables;
mod work;

// The test-only dump of the parity tools; the release build has no dump (AD-323).
#[cfg(feature = "dump")]
pub mod dump;

pub use import_survey::reply::{decode, typed_reply, SURVEY_SECTIONS};

/// The test features of this build. A build with one of them is refused by `archkeel-collect`
/// (AD-406). The release build has none.
pub const TEST_FEATURES: &[&str] = if cfg!(feature = "dump") {
    &["dump"]
} else {
    &[]
};

/// The version and the workspace code digest that `build.rs` records, and the compiler.
const BUILD: (&str, &str) = (env!("ARCHKEEL_VERSION"), env!("ARCHKEEL_CODE_DIGEST"));
const COMPILER: (&str, &str) = (
    env!("ARCHKEEL_RUSTC_VERSION"),
    env!("CARGO_PKG_RUST_VERSION"),
);

/// The provenance of this build: the collector of the Dart profile (AD-468).
pub fn provenance() -> archkeel_facts::envelope::Provenance {
    archkeel_facts::envelope::Provenance::native(
        archkeel_facts::envelope::Profile::Dart,
        BUILD,
        COMPILER,
    )
}
pub use import_survey::{
    survey, GapName, NamedGap, PartOwner, Survey, PARSE_BUDGET_BYTES, PARSE_BUDGET_TOKENS,
    SURVEY_BUDGET_BYTES,
};

#[cfg(test)]
#[path = "lib_tests.rs"]
mod tests;
