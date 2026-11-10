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

use archkeel_facts::{IntoSection, Section};
use serde::ser::{SerializeMap, Serializer};
use serde::Serialize;
use serde_json::Value;

use crate::pieces::{Adler, Piece, ZLIB_HEADER};
use crate::protocol::Version;
use crate::reply::{Facts, Record, ReplySection};
use archkeel_facts::envelope::{
    Capabilities, Coverage, Evidence, FileFact, Input, NoEntries, ProtocolVersion, Provenance,
    Source, State, Target,
};

/// What the reply says before the records: who made it, what it declares, and the small lists.
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
    pub files: Vec<FileFact>,
    pub imports: Vec<Target>,
}

/// What the reply says after the records.
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

/// The function that a section gives each record to.
pub type Emit<'e> = &'e mut dyn FnMut(&Record);

/// The function that a typed section gives each record of archkeel-facts to (AD-345).
pub type TypedEmit<'e, D> = &'e mut dyn FnMut(&archkeel_facts::Record<D>);

/// The function that fills a section: it gives each record to the function it is called with.
type Fill<'f, T> = &'f mut dyn FnMut(&mut dyn FnMut(&T));

/// Where the records of a section go: the compressed reply, or the lists of a test.
pub trait SectionSink {
    /// Take the next section, with records of archkeel-facts. The types write the wire.
    fn typed_section<D: IntoSection>(
        &mut self,
        name: &'static str,
        fill: &mut dyn FnMut(TypedEmit<'_, D>),
    ) -> io::Result<()>;

    /// `typed_section` with a function that is called once.
    fn write_typed_section<D: IntoSection>(
        &mut self,
        name: &'static str,
        fill: impl FnOnce(TypedEmit<'_, D>),
    ) -> io::Result<()>
    where
        Self: Sized,
    {
        let mut fill = Some(fill);
        self.typed_section(name, &mut |emit| {
            if let Some(fill) = fill.take() {
                fill(emit);
            }
        })
    }

    /// Take the next section. `fill` makes the records and gives each to the function it is called
    /// with.
    fn section(&mut self, name: &'static str, fill: &mut dyn FnMut(Emit<'_>)) -> io::Result<()>;

    /// `section` with a function that is called once.
    fn write_section(
        &mut self,
        name: &'static str,
        fill: impl FnOnce(&mut dyn FnMut(&Record)),
    ) -> io::Result<()>
    where
        Self: Sized,
    {
        let mut fill = Some(fill);
        self.section(name, &mut |emit| {
            if let Some(fill) = fill.take() {
                fill(emit);
            }
        })
    }
}

impl SectionSink for Sections<'_> {
    /// The name must be the next one that the head declared.
    fn section(&mut self, name: &'static str, fill: &mut dyn FnMut(Emit<'_>)) -> io::Result<()> {
        self.records(name, fill, write_record)
    }

    fn typed_section<D: IntoSection>(
        &mut self,
        name: &'static str,
        fill: &mut dyn FnMut(TypedEmit<'_, D>),
    ) -> io::Result<()> {
        self.records(name, fill, |out, record| {
            Ok(serde_json::to_writer(out, record)?)
        })
    }
}

impl Sections<'_> {
    /// Write the next declared section: its name and each record that `fill` gives.
    fn records<T>(
        &mut self,
        name: &'static str,
        fill: Fill<'_, T>,
        write: fn(&mut Piece, &T) -> io::Result<()>,
    ) -> io::Result<()> {
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
        fill(&mut |record: &T| {
            if failure.is_some() {
                return;
            }
            let comma = if first { Ok(()) } else { out.write_all(b",") };
            first = false;
            failure = comma.and_then(|()| write(out, record)).err();
        });
        if let Some(error) = failure {
            return Err(error);
        }
        self.out.write_all(b"]")?;
        section.close(&mut *self.out)
    }
}

/// Give the records of a typed section to the sink.
fn write_typed(sink: &mut impl SectionSink, section: Section) -> io::Result<()> {
    fn put<S: SectionSink, D: IntoSection>(
        sink: &mut S,
        name: &'static str,
        records: Vec<archkeel_facts::Record<D>>,
    ) -> io::Result<()> {
        sink.write_typed_section(name, |emit| records.iter().for_each(emit))
    }
    let name = section.name();
    match section {
        Section::Imports(records) => put(sink, name, records),
        Section::Symbols(records) => put(sink, name, records),
        Section::Calls(records) => put(sink, name, records),
        Section::References(records) => put(sink, name, records),
        Section::Bindings(records) => put(sink, name, records),
        Section::Constructs(records) => put(sink, name, records),
        Section::TypingSignals(records) => put(sink, name, records),
        Section::Unknowns(records) => put(sink, name, records),
    }
}

/// Encode the reply for `version`; 8.0.0 and 9.0.0 share one compressed shape. The facts are
/// written section by section through `stream::encode_stream`, which holds the whole reply only as
/// compressed bytes.
pub fn encode(version: Version, facts: Facts) -> Result<Vec<u8>, String> {
    let Facts {
        provenance,
        git_head,
        dirty,
        scope,
        sections,
        features,
        constructs,
        inputs,
        files,
        imports,
        selected_files,
        files_read,
        gaps,
        evidence,
    } = facts;
    let head = Head {
        provenance,
        git_head,
        dirty,
        scope,
        sections: sections.iter().map(ReplySection::name).collect(),
        features,
        constructs,
        inputs,
        files,
        imports,
    };
    let mut bytes = Vec::new();
    encode_stream(version, head, &mut bytes, |writer| {
        for section in sections {
            match section {
                ReplySection::Typed(section) => write_typed(writer, section)?,
                ReplySection::Records(name, records) => {
                    writer.write_section(name, |emit| records.iter().for_each(emit))?;
                }
            }
        }
        Ok(Tail {
            selected_files,
            files_read,
            gaps,
            evidence,
        })
    })?;
    Ok(bytes)
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

/// The text up to the records: the keys of `facts` that come before `sections`, in the order of
/// the Python reply, and the opening of the list of sections. The envelope types write the keys.
fn write_before(out: &mut Piece, head: &Head, tail: Tail) -> io::Result<()> {
    let capabilities =
        Capabilities::of(&head.sections, &head.features, &head.constructs).map_err(invalid)?;
    let coverage = Coverage::of(
        (tail.files_read, head.files.len()),
        tail.selected_files,
        tail.gaps,
    );
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
    facts.serialize_entry("evidence", &tail.evidence)?;
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
    let source =
        Source::of((&head.git_head, &head.dirty), &head.scope, &head.inputs).map_err(invalid)?;
    let protocol_version = ProtocolVersion::parse(version.as_str()).ok_or_else(|| {
        invalid(format!(
            "no compressed reply for version {}",
            version.as_str()
        ))
    })?;
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

/// One record, with the order of keys of `record_value` and without a copy of its data.
fn write_record(out: &mut impl Write, record: &Record) -> io::Result<()> {
    let mut item = Fields::open(out)?;
    item.put(out, "id", &record.id)?;
    item.put(out, "evidence_class", &record.evidence_class)?;
    item.put(out, "area", &record.area)?;
    item.put(out, "kind", &record.kind)?;
    item.put(out, "title", &record.title)?;
    item.put(out, "subjects", &record.subjects)?;
    item.put(out, "evidence_ids", &record.evidence_ids)?;
    item.put(out, "rule_ids", &Vec::<String>::new())?;
    item.put(out, "fact_ids", &record.fact_ids)?;
    item.put(out, "provenance", &Vec::<String>::new())?;
    item.put(out, "data", &record.data)?;
    item.close(out)
}
