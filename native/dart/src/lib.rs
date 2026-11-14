// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The native Dart collector of Archkeel as a library (#880, AD-450).
//!
//! `survey` gives the typed import survey of one request: the selected sources, the file facts,
//! the part owners, the import records with their targets and the named gaps. `typed_reply`
//! assembles it as a reply with the sections `imports` and `unknowns`. The binary
//! `archkeel-dart-collector` decodes a request and still writes no reply, and `archkeel-collect`
//! does not link this crate yet, so no Dart project gets a verdict.

#![forbid(unsafe_code)]
#![deny(unreachable_pub)]
// The survey parses directives only. The full parse of definitions and sites serves the dump until a later slice of #880 surveys symbols; the expectation fails once it is used.
#![cfg_attr(
    not(feature = "dump"),
    expect(
        dead_code,
        reason = "the full parse serves the dump until a slice of #880 surveys symbols (AD-450)"
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
#[cfg(feature = "dump")]
pub mod dump;
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
mod survey;
mod syntax;
mod tree;
mod unicode_tables;
mod work;

use archkeel_facts::envelope::{Profile, Provenance, Reply};
use archkeel_facts::request::DartRequest;
use archkeel_facts::{GapFact, ImportFact};
use archkeel_wire::protocol::Version;
use archkeel_wire::stream::{Head, SectionSink, Tail};

pub use survey::{survey, GapName, NamedGap, PartOwner, Survey, PARSE_BUDGET_BYTES};

/// The sections of the survey reply, in their order. No other section is collected.
pub const SURVEY_SECTIONS: [&str; 2] = ["imports", "unknowns"];

/// The test features of this build. The release build has none.
pub const TEST_FEATURES: &[&str] = if cfg!(feature = "dump") {
    &["dump"]
} else {
    &[]
};

/// The provenance of this build: the collector of the Dart profile with the code digest of the
/// workspace.
pub fn provenance() -> Provenance {
    Provenance::native(
        Profile::Dart,
        (env!("ARCHKEEL_VERSION"), env!("ARCHKEEL_CODE_DIGEST")),
        (
            env!("ARCHKEEL_RUSTC_VERSION"),
            env!("CARGO_PKG_RUST_VERSION"),
        ),
    )
}

/// Decode a Dart request with the shared wire, as the binary reads it on stdin.
pub fn decode(payload: &[u8]) -> Result<DartRequest, String> {
    archkeel_wire::request::decode_dart(payload)
}

/// The typed reply of one request: the survey with the sections `imports` and `unknowns`.
pub fn typed_reply(
    request: &DartRequest,
    provenance: Provenance,
    version: Version,
) -> Result<Reply, String> {
    let found = survey(request)?;
    let head = Head {
        provenance,
        git_head: request.snapshot.git_head.clone(),
        dirty: serde_json::to_value(&request.snapshot.dirty).map_err(|error| error.to_string())?,
        scope: found.scope,
        sections: SURVEY_SECTIONS.to_vec(),
        features: Vec::new(),
        constructs: Vec::new(),
        inputs: found.inputs,
        source_digest: None,
        files: found.files,
        imports: found.targets,
    };
    let imports = found.imports;
    let tail = Tail {
        selected_files: found.coverage.selected_files,
        files_read: usize::try_from(found.coverage.files_read).map_err(|e| e.to_string())?,
        gaps: found.unknowns,
        evidence: found.evidence,
    };
    archkeel_wire::typed::assemble(version, head, |writer| {
        writer.write_typed_section::<ImportFact>(|emit| imports.iter().for_each(emit))?;
        writer.write_typed_section::<GapFact>(|emit| tail.gaps.iter().for_each(emit))?;
        Ok(tail)
    })
}

#[cfg(test)]
#[path = "lib_tests.rs"]
mod tests;
