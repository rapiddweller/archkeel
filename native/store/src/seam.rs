// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The read-set document for the Python shell (AD-346, owner decision of 2026-11-10).
//!
//! It is the reply with each record of a measured section in its read-set form
//! (`archkeel_facts::readset`): the data holds only the fields that a rule or a view reads for its
//! area and kind (WP1). The evidence class follows from the section, which the store validated.
//! The gaps of the coverage and of the `unknowns` section keep their wire form: they are few, and
//! diagnostics show their title. The envelope of the reply is small and is written whole; the
//! evidence keeps its excerpt (4.8 % of the bytes on x35, WP2).

use archkeel_facts::envelope::{
    Adapter, Capabilities, Evidence, FileFact, Input, NoEntries, Profile, ProtocolVersion, Reply,
    Runtime, Source, State, Target,
};
use archkeel_facts::readset;
use archkeel_facts::{GapFact, Record, Section};
use std::io::Write;

use serde::{Serialize, Serializer};

/// A measured section in its read-set form; the `unknowns` section keeps its wire form.
struct SectionEntry<'a>(&'a Section);

impl Serialize for SectionEntry<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        match self.0 {
            Section::Unknowns(_) => self.0.serialize(serializer),
            section => readset::Of(section).serialize(serializer),
        }
    }
}

struct Sections<'a>(&'a [Section]);

impl Serialize for Sections<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.collect_seq(self.0.iter().map(SectionEntry))
    }
}

#[derive(Serialize)]
struct CoverageEntry<'a> {
    selected_files: &'a [String],
    files_read: u64,
    files_parsed: u64,
    full_scope: bool,
    gaps: &'a [Record<GapFact>],
}

#[derive(Serialize)]
struct FactsEntry<'a> {
    profile: Profile,
    adapter: &'a Adapter,
    runtime: &'a Runtime,
    source: &'a Source,
    capabilities: &'a Capabilities,
    inputs: &'a [Input],
    files: &'a [FileFact],
    imports: &'a [Target],
    sections: Sections<'a>,
    coverage: CoverageEntry<'a>,
    evidence: &'a [Evidence],
    uncertain_reexports: NoEntries,
    type_shapes: NoEntries,
    state: &'a State,
    candidate_evidence: NoEntries,
    provider_bindings: NoEntries,
}

#[derive(Serialize)]
struct Document<'a> {
    protocol_version: ProtocolVersion,
    provider_sources: NoEntries,
    facts: FactsEntry<'a>,
}

/// Write the read-set document of a decoded reply as one answer frame. The document is written
/// twice: once to count its length for the frame header, once to `output`. It is never held.
pub(crate) fn write_frame(reply: &Reply, output: &mut impl Write) -> Result<(), String> {
    let mut count = crate::Count(0);
    serde_json::to_writer(&mut count, &document(reply)).map_err(|error| error.to_string())?;
    output.write_all(b"O").map_err(|error| error.to_string())?;
    output
        .write_all(&count.0.to_be_bytes())
        .map_err(|error| error.to_string())?;
    serde_json::to_writer(&mut *output, &document(reply)).map_err(|error| error.to_string())?;
    output.flush().map_err(|error| error.to_string())
}

fn document(reply: &Reply) -> Document<'_> {
    let facts = &reply.facts;
    Document {
        protocol_version: reply.protocol_version,
        provider_sources: NoEntries,
        facts: FactsEntry {
            profile: facts.profile,
            adapter: &facts.adapter,
            runtime: &facts.runtime,
            source: &facts.source,
            capabilities: &facts.capabilities,
            inputs: &facts.inputs,
            files: &facts.files,
            imports: &facts.imports,
            sections: Sections(&facts.sections),
            coverage: CoverageEntry {
                selected_files: &facts.coverage.selected_files,
                files_read: facts.coverage.files_read,
                files_parsed: facts.coverage.files_parsed,
                full_scope: facts.coverage.full_scope,
                gaps: &facts.coverage.gaps,
            },
            evidence: &facts.evidence,
            uncertain_reexports: NoEntries,
            type_shapes: NoEntries,
            state: &facts.state,
            candidate_evidence: NoEntries,
            provider_bindings: NoEntries,
        },
    }
}
