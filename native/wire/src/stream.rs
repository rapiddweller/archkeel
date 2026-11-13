// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reply of protocols 8.0.0 and 9.0.0, written section by section into the compressor.
//!
//! A reply with a tree of all facts is several times the size of the facts, and a list of all
//! records of a project is large too. Each record of a section is written when the caller makes it
//! and is dropped after that. The reply is held only as compressed bytes.
//!
//! The keys of `facts` have the order of the Python reply (`sort_keys`), so `evidence` comes
//! before `sections`. The evidence is complete only after the last record was made, so the reply
//! has three pieces: the text before the records (with the evidence), the records, and the text
//! after them. The records are compressed first, as a piece of raw deflate blocks of their own,
//! and the pieces are joined in the order of the text, with one zlib header and one checksum. A
//! decoder reads the join as one stream.
//!
//! The sections that the head declares must be written, in that order, and no other: a reply that
//! declares a section that it does not hold, or holds one that it does not declare, is an error and
//! never reaches the host.

use std::io::{self, Write};

use archkeel_facts::IntoSection;
use serde::ser::{SerializeMap, Serializer};
use serde::Serialize;
use serde_json::Value;

use crate::pieces::{Adler, Piece, ZLIB_HEADER};
use crate::protocol::Version;
use archkeel_facts::envelope::{
    Capabilities, Coverage, Evidence, FileFact, Input, NoEntries, ProtocolVersion, Provenance,
    Source, State, Target,
};

/// What the reply says before the records: who made it, what it declares, and the small lists.
#[derive(Clone)]
pub struct Head {
    pub provenance: Provenance,
    pub git_head: String,
    pub dirty: Value,
    pub scope: Vec<String>,
    /// The sections that the capability declares, in the order that they are written.
    pub sections: Vec<&'static str>,
    pub features: Vec<&'static str>,
    pub constructs: Vec<(&'static str, &'static str)>,
    pub inputs: Vec<Input>,
    /// The source digest of a collector that digests its inputs in its own way, as the Python
    /// collector does (`collect._inputs`). `None` is the digest of the input listing.
    pub source_digest: Option<String>,
    pub files: Vec<FileFact>,
    pub imports: Vec<Target>,
}

/// What the reply says after the records.
#[derive(Clone)]
pub struct Tail {
    pub selected_files: Vec<String>,
    pub files_read: usize,
    /// Coverage gaps. The collection is complete only when there is none.
    pub gaps: Vec<archkeel_facts::Record<archkeel_facts::GapFact>>,
    pub evidence: Vec<Evidence>,
}

/// The writer of the sections of one reply.
pub struct Sections<'a> {
    out: &'a mut Piece,
    expected: Vec<&'static str>,
    written: usize,
}

/// The function that a section gives each record of archkeel-facts to (AD-345).
pub type TypedEmit<'e, D> = &'e mut dyn FnMut(&archkeel_facts::Record<D>);

/// Where the records of a section go: the compressed reply, or the lists of a test.
pub trait SectionSink {
    /// Take the next section, with records of archkeel-facts. The data type decides the name of the
    /// section (`IntoSection::section_name()`), and the types write the wire.
    fn typed_section<D: IntoSection>(
        &mut self,
        fill: &mut dyn FnMut(TypedEmit<'_, D>),
    ) -> io::Result<()>;

    /// `typed_section` with a function that is called once.
    fn write_typed_section<D: IntoSection>(
        &mut self,
        fill: impl FnOnce(TypedEmit<'_, D>),
    ) -> io::Result<()>
    where
        Self: Sized,
    {
        let mut fill = Some(fill);
        self.typed_section(&mut |emit| {
            if let Some(fill) = fill.take() {
                fill(emit);
            }
        })
    }
}

impl SectionSink for Sections<'_> {
    /// The section must be the next one that the head declared.
    fn typed_section<D: IntoSection>(
        &mut self,
        fill: &mut dyn FnMut(TypedEmit<'_, D>),
    ) -> io::Result<()> {
        let name = D::section_name();
        if self.expected.get(self.written) != Some(&name) {
            let reason = format!("the section {name} is not the next declared section");
            return Err(io::Error::new(io::ErrorKind::InvalidData, reason));
        }
        if self.written > 0 {
            self.out.write_all(b",")?;
        }
        self.written += 1;
        let mut section = Fields::open(&mut *self.out)?;
        section.put(&mut *self.out, "name", &name)?;
        section.key(&mut *self.out, "records")?;
        self.out.write_all(b"[")?;
        let mut first = true;
        let mut failure = None;
        let out = &mut *self.out;
        fill(&mut |record: &archkeel_facts::Record<D>| {
            if failure.is_some() {
                return;
            }
            let comma = if first { Ok(()) } else { out.write_all(b",") };
            first = false;
            failure = comma
                .and_then(|()| Ok(serde_json::to_writer(&mut *out, record)?))
                .err();
        });
        if let Some(error) = failure {
            return Err(error);
        }
        self.out.write_all(b"]")?;
        section.close(&mut *self.out)
    }
}

/// Encode a reply for `version` into `sink`. `produce` writes the sections and returns the tail.
/// The records are compressed as they are made; the rest of the reply is written after them, with
/// the evidence before the records, as the Python reply has it.
pub fn encode_stream<W: Write>(
    version: Version,
    head: Head,
    mut sink: W,
    produce: impl FnOnce(&mut Sections<'_>) -> io::Result<Tail>,
) -> Result<(), String> {
    if version == Version::V3 {
        return Err("a native collector writes only the compressed reply".to_owned());
    }
    let failed = |error: io::Error| format!("cannot write the reply: {error}");
    let mut records = Piece::new();
    let expected = head.sections.clone();
    let mut sections = Sections {
        out: &mut records,
        expected,
        written: 0,
    };
    let tail = produce(&mut sections).map_err(failed)?;
    if sections.written != sections.expected.len() {
        let reason = "a declared section was not written".to_owned();
        return Err(format!("cannot write the reply: {reason}"));
    }
    let (mut before, mut after) = (Piece::new(), Piece::new());
    write_before(&mut before, &head, tail).map_err(failed)?;
    write_after(&mut after, &head, version).map_err(failed)?;
    let (before, records, after) = (
        before.close(false).map_err(failed)?,
        records.close(false).map_err(failed)?,
        after.close(true).map_err(failed)?,
    );
    let inner = Adler::join(before.adler, records.adler, records.length);
    let whole = Adler::join(inner, after.adler, after.length);
    sink.write_all(&ZLIB_HEADER).map_err(failed)?;
    for part in [&before.bytes, &records.bytes, &after.bytes] {
        sink.write_all(part).map_err(failed)?;
    }
    sink.write_all(&whole.to_be_bytes()).map_err(failed)?;
    sink.flush().map_err(failed)
}

/// The state of a JSON object that is written key by key into `out`.
struct Fields {
    first: bool,
}

impl Fields {
    fn open(out: &mut impl Write) -> io::Result<Self> {
        out.write_all(b"{")?;
        Ok(Self { first: true })
    }

    fn key(&mut self, out: &mut impl Write, name: &str) -> io::Result<()> {
        if !self.first {
            out.write_all(b",")?;
        }
        self.first = false;
        serde_json::to_writer(&mut *out, name)?;
        out.write_all(b":")
    }

    fn put(&mut self, out: &mut impl Write, name: &str, value: &impl Serialize) -> io::Result<()> {
        self.key(out, name)?;
        Ok(serde_json::to_writer(out, value)?)
    }

    fn close(self, out: &mut impl Write) -> io::Result<()> {
        out.write_all(b"}")
    }
}

/// The keys of `facts` after the sections, in the order of the Python reply.
#[derive(Serialize)]
struct After<'a> {
    source: &'a Source,
    state: State,
    type_shapes: NoEntries,
    uncertain_reexports: NoEntries,
}

/// The keys of the reply after `facts`.
#[derive(Serialize)]
struct Trailer {
    protocol_version: ProtocolVersion,
    provider_sources: NoEntries,
}

fn invalid(reason: String) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason)
}

/// The capabilities and the coverage of a reply. The stream and the typed reply (`typed.rs`) both
/// take them from here, so the two forms cannot say different things.
pub(crate) fn counted(
    head: &Head,
    tail: Tail,
) -> io::Result<(Capabilities, Coverage, Vec<Evidence>)> {
    let capabilities =
        Capabilities::of(&head.sections, &head.features, &head.constructs).map_err(invalid)?;
    let coverage = Coverage::of(
        (tail.files_read, head.files.len()),
        tail.selected_files,
        tail.gaps,
    );
    Ok((capabilities, coverage, tail.evidence))
}

/// The source of a reply: the request identity and the digest of the inputs.
pub(crate) fn source_of(head: &Head) -> io::Result<Source> {
    let mut source =
        Source::of((&head.git_head, &head.dirty), &head.scope, &head.inputs).map_err(invalid)?;
    if let Some(digest) = &head.source_digest {
        source.source_digest.clone_from(digest);
    }
    Ok(source)
}

/// The protocol version of the compressed reply of `version`.
pub(crate) fn compressed(version: Version) -> io::Result<ProtocolVersion> {
    version.compressed().ok_or_else(|| {
        invalid(format!(
            "no compressed reply for version {}",
            version.as_str()
        ))
    })
}

/// The text up to the records: the keys of `facts` that come before `sections`, in the order of
/// the Python reply, and the opening of the list of sections. The envelope types write the keys.
fn write_before(out: &mut Piece, head: &Head, tail: Tail) -> io::Result<()> {
    let (capabilities, coverage, evidence) = counted(head, tail)?;
    let Provenance {
        profile,
        adapter,
        runtime,
    } = &head.provenance;
    out.write_all(b"{\"facts\":")?;
    // The object stays open: `end` would close it, and the sections and the rest follow.
    let mut serializer = serde_json::Serializer::new(&mut *out);
    let mut facts = serializer.serialize_map(None)?;
    facts.serialize_entry("adapter", adapter)?;
    facts.serialize_entry("candidate_evidence", &NoEntries)?;
    facts.serialize_entry("capabilities", &capabilities)?;
    facts.serialize_entry("coverage", &coverage)?;
    facts.serialize_entry("evidence", &evidence)?;
    facts.serialize_entry("files", &head.files)?;
    facts.serialize_entry("imports", &head.imports)?;
    facts.serialize_entry("inputs", &head.inputs)?;
    facts.serialize_entry("profile", profile)?;
    facts.serialize_entry("provider_bindings", &NoEntries)?;
    facts.serialize_entry("runtime", runtime)?;
    out.write_all(b",\"sections\":[")
}

/// The fields of a small object, without its braces.
fn write_fields(out: &mut Piece, value: &impl Serialize) -> io::Result<()> {
    let text = serde_json::to_vec(value)?;
    out.write_all(&text[1..text.len() - 1])
}

/// The text after the records: the end of the list of sections, the keys of `facts` that come
/// after `sections`, and the keys of the reply that come after `facts`.
fn write_after(out: &mut Piece, head: &Head, version: Version) -> io::Result<()> {
    let source = source_of(head)?;
    let protocol_version = compressed(version)?;
    out.write_all(b"],")?;
    let after = After {
        source: &source,
        state: State::default(),
        type_shapes: NoEntries,
        uncertain_reexports: NoEntries,
    };
    write_fields(out, &after)?;
    out.write_all(b"},")?;
    let trailer = Trailer {
        protocol_version,
        provider_sources: NoEntries,
    };
    write_fields(out, &trailer)?;
    out.write_all(b"}")
}

#[cfg(test)]
#[path = "stream_tests.rs"]
mod tests;
