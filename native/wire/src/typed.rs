// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed reply of a collector that runs in the process of the core (AD-406).
//!
//! The producer of a collector gives its sections to a `SectionSink`. `stream.rs` writes them
//! into the compressed bytes of a subprocess reply; `assemble` here keeps them as the typed
//! `Reply` that the store decodes from those bytes. Both take the capabilities, the coverage, the
//! source and the protocol version from the same functions of `stream.rs`, and the same order
//! check of the declared sections, so the two forms of one collection say the same thing. The
//! byte comparison of the two forms is in `typed_tests.rs` and in the tests of `archkeel-collect`.

use std::io;

use archkeel_facts::envelope::{Facts, NoEntries, Reply, State};
use archkeel_facts::{IntoSection, Record, Section};

use crate::protocol::Version;
use crate::stream::{compressed, counted, source_of, Head, SectionSink, Tail, TypedEmit};

/// The sections of one typed reply, in the order that the head declared.
pub struct TypedSections {
    expected: Vec<&'static str>,
    sections: Vec<Section>,
}

impl SectionSink for TypedSections {
    /// The section must be the next one that the head declared, as for the stream.
    fn typed_section<D: IntoSection>(
        &mut self,
        fill: &mut dyn FnMut(TypedEmit<'_, D>),
    ) -> io::Result<()> {
        let name = D::section_name();
        if self.expected.get(self.sections.len()) != Some(&name) {
            let reason = format!("the section {name} is not the next declared section");
            return Err(io::Error::new(io::ErrorKind::InvalidData, reason));
        }
        let mut records: Vec<Record<D>> = Vec::new();
        fill(&mut |record: &Record<D>| records.push(record.clone()));
        self.sections.push(D::section(records));
        Ok(())
    }
}

/// The typed reply for `version`. `produce` gives the sections and returns the tail, as for
/// `encode_stream`. A section that the head declares and `produce` does not give is an error.
pub fn assemble(
    version: Version,
    head: Head,
    produce: impl FnOnce(&mut TypedSections) -> io::Result<Tail>,
) -> Result<Reply, String> {
    let failed = |error: io::Error| format!("cannot assemble the reply: {error}");
    let protocol_version = compressed(version).map_err(failed)?;
    let mut sections = TypedSections {
        expected: head.sections.clone(),
        sections: Vec::new(),
    };
    let tail = produce(&mut sections).map_err(failed)?;
    if sections.sections.len() != sections.expected.len() {
        return Err("cannot assemble the reply: a declared section was not given".to_owned());
    }
    let (capabilities, coverage, evidence) = counted(&head, tail).map_err(failed)?;
    let source = source_of(&head).map_err(failed)?;
    let Head {
        provenance,
        inputs,
        files,
        imports,
        ..
    } = head;
    Ok(Reply {
        protocol_version,
        provider_sources: NoEntries,
        facts: Facts {
            profile: provenance.profile,
            profile_limits: None,
            adapter: provenance.adapter,
            runtime: provenance.runtime,
            source,
            capabilities,
            inputs,
            files,
            imports,
            sections: sections.sections,
            coverage,
            evidence,
            uncertain_reexports: NoEntries,
            type_shapes: NoEntries,
            state: State::default(),
            candidate_evidence: NoEntries,
            provider_bindings: NoEntries,
        },
    })
}

#[cfg(test)]
#[path = "typed_tests.rs"]
mod tests;
