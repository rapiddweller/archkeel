// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reply of protocols 8.0.0 and 9.0.0, written section by section into the compressor.
//!
//! A reply with a tree of all facts is several times the size of the facts, and a list of all
//! records of a project is large too. Here the head of the facts is written first, each record of a
//! section is written when the caller makes it and is dropped after that, and the coverage and the
//! evidence follow. The reply is held only as compressed bytes.
//!
//! The sections that the head declares must be written, in that order, and no other: a reply that
//! declares a section that it does not hold, or holds one that it does not declare, is an error and
//! never reaches the host.

use std::io::{self, BufWriter, Write};

use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde::Serialize;
use serde_json::{json, Value};

use crate::protocol::Version;
use crate::reply::{
    evidence_value, file_value, source_digest, target_value, Evidence, Facts, FileFact, Input,
    Provenance, Record, Target,
};

type Out = BufWriter<ZlibEncoder<Vec<u8>>>;

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
    pub gaps: Vec<Record>,
    pub evidence: Vec<Evidence>,
}

/// The writer of the sections of one reply.
pub struct Sections<'a> {
    out: &'a mut Out,
    expected: Vec<&'static str>,
    written: usize,
}

impl Sections<'_> {
    /// Write the next section. `fill` makes the records and gives each to the function it is
    /// called with. The name must be the next one that the head declared.
    pub fn section(
        &mut self,
        name: &'static str,
        fill: impl FnOnce(&mut dyn FnMut(&Record)),
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
        fill(&mut |record: &Record| {
            if failure.is_some() {
                return;
            }
            let comma = if first { Ok(()) } else { out.write_all(b",") };
            first = false;
            failure = comma.and_then(|()| write_record(out, record)).err();
        });
        if let Some(error) = failure {
            return Err(error);
        }
        self.out.write_all(b"]")?;
        section.close(&mut *self.out)
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
        sections: sections.iter().map(|(name, _)| *name).collect(),
        features,
        constructs,
        inputs,
        files,
        imports,
    };
    encode_stream(version, head, |writer| {
        for (name, records) in sections {
            writer.section(name, |emit| records.iter().for_each(emit))?;
        }
        Ok(Tail {
            selected_files,
            files_read,
            gaps,
            evidence,
        })
    })
}

/// Encode a reply for `version`. `produce` writes the sections and returns the tail.
pub fn encode_stream(
    version: Version,
    head: Head,
    produce: impl FnOnce(&mut Sections<'_>) -> io::Result<Tail>,
) -> Result<Vec<u8>, String> {
    if version == Version::V3 {
        return Err("a native collector writes only the compressed reply".to_owned());
    }
    let encoder = ZlibEncoder::new(Vec::new(), Compression::new(1));
    let mut out = BufWriter::with_capacity(1 << 16, encoder);
    write_reply(&mut out, version, head, produce)
        .map_err(|error| format!("cannot write the reply: {error}"))?;
    let encoder = out
        .into_inner()
        .map_err(|error| format!("cannot write the reply: {error}"))?;
    encoder
        .finish()
        .map_err(|error| format!("cannot compress the reply: {error}"))
}

/// The state of a JSON object that is written key by key into `out`.
struct Fields {
    first: bool,
}

impl Fields {
    fn open(out: &mut Out) -> io::Result<Self> {
        out.write_all(b"{")?;
        Ok(Self { first: true })
    }

    fn key(&mut self, out: &mut Out, name: &str) -> io::Result<()> {
        if !self.first {
            out.write_all(b",")?;
        }
        self.first = false;
        serde_json::to_writer(&mut *out, name)?;
        out.write_all(b":")
    }

    fn put(&mut self, out: &mut Out, name: &str, value: &impl Serialize) -> io::Result<()> {
        self.key(out, name)?;
        Ok(serde_json::to_writer(out, value)?)
    }

    fn list<T>(
        &mut self,
        out: &mut Out,
        name: &str,
        items: impl IntoIterator<Item = T>,
        mut write: impl FnMut(&mut Out, T) -> io::Result<()>,
    ) -> io::Result<()> {
        self.key(out, name)?;
        out.write_all(b"[")?;
        for (index, item) in items.into_iter().enumerate() {
            if index > 0 {
                out.write_all(b",")?;
            }
            write(out, item)?;
        }
        out.write_all(b"]")
    }

    fn close(self, out: &mut Out) -> io::Result<()> {
        out.write_all(b"}")
    }
}

fn write_reply(
    out: &mut Out,
    version: Version,
    head: Head,
    produce: impl FnOnce(&mut Sections<'_>) -> io::Result<Tail>,
) -> io::Result<()> {
    let mut reply = Fields::open(out)?;
    reply.put(out, "protocol_version", &version.as_str())?;
    reply.put(out, "provider_sources", &Vec::<Value>::new())?;
    reply.key(out, "facts")?;
    let mut facts = Fields::open(out)?;
    let files_parsed = head.files.len();
    let expected = head.sections.clone();
    write_head(out, &mut facts, head)?;
    facts.key(out, "sections")?;
    out.write_all(b"[")?;
    let mut sections = Sections {
        out,
        expected,
        written: 0,
    };
    let tail = produce(&mut sections)?;
    if sections.written != sections.expected.len() {
        let reason = "a declared section was not written".to_owned();
        return Err(io::Error::new(io::ErrorKind::InvalidData, reason));
    }
    out.write_all(b"]")?;
    write_tail(out, &mut facts, tail, files_parsed)?;
    facts.close(out)?;
    reply.close(out)
}

/// The fields of the facts before the sections.
fn write_head(out: &mut Out, facts: &mut Fields, head: Head) -> io::Result<()> {
    let provenance = &head.provenance;
    facts.put(out, "profile", &provenance.profile)?;
    facts.key(out, "adapter")?;
    let mut adapter = Fields::open(out)?;
    adapter.put(out, "name", &provenance.profile)?;
    adapter.put(out, "version", &provenance.adapter_version)?;
    adapter.put(out, "code_digest", &provenance.code_digest)?;
    adapter.close(out)?;
    facts.key(out, "runtime")?;
    let mut runtime = Fields::open(out)?;
    runtime.put(out, "name", &provenance.runtime_name)?;
    runtime.put(out, "version", &provenance.runtime_version)?;
    runtime.put(out, "required", &provenance.runtime_required)?;
    runtime.put(out, "requirement_state", &"declared")?;
    runtime.close(out)?;
    facts.key(out, "source")?;
    let mut source = Fields::open(out)?;
    source.put(out, "git_head", &head.git_head)?;
    source.put(out, "dirty", &head.dirty)?;
    source.put(out, "source_digest", &source_digest(&head.inputs))?;
    source.put(out, "scope", &head.scope)?;
    source.close(out)?;
    facts.key(out, "capabilities")?;
    let mut capabilities = Fields::open(out)?;
    capabilities.put(out, "sections", &head.sections)?;
    capabilities.put(out, "resolution_features", &head.features)?;
    let constructs = head
        .constructs
        .iter()
        .map(|(name, status)| json!({"name": name, "status": status}));
    capabilities.list(out, "constructs", constructs, |out, item| {
        Ok(serde_json::to_writer(out, &item)?)
    })?;
    capabilities.close(out)?;
    facts.list(out, "inputs", &head.inputs, |out, input| {
        let value = json!({
            "path": input.path, "digest": input.digest, "role": input.role.as_str(),
        });
        Ok(serde_json::to_writer(out, &value)?)
    })?;
    facts.list(out, "files", &head.files, |out, file| {
        Ok(serde_json::to_writer(out, &file_value(file))?)
    })?;
    facts.list(out, "imports", &head.imports, |out, target| {
        Ok(serde_json::to_writer(out, &target_value(target))?)
    })
}

/// The coverage, the evidence and the fields that a native collector leaves empty.
fn write_tail(
    out: &mut Out,
    facts: &mut Fields,
    tail: Tail,
    files_parsed: usize,
) -> io::Result<()> {
    facts.key(out, "coverage")?;
    let mut coverage = Fields::open(out)?;
    coverage.put(out, "selected_files", &tail.selected_files)?;
    coverage.put(out, "files_read", &tail.files_read)?;
    coverage.put(out, "files_parsed", &files_parsed)?;
    coverage.put(out, "full_scope", &tail.gaps.is_empty())?;
    coverage.list(out, "gaps", &tail.gaps, write_record)?;
    coverage.close(out)?;
    facts.list(out, "evidence", &tail.evidence, |out, item| {
        Ok(serde_json::to_writer(out, &evidence_value(item))?)
    })?;
    let empty = Vec::<Value>::new();
    facts.put(out, "uncertain_reexports", &empty)?;
    facts.put(out, "type_shapes", &empty)?;
    facts.put(out, "state", &json!({"classes": [], "functions": []}))?;
    facts.put(out, "candidate_evidence", &empty)?;
    facts.put(out, "provider_bindings", &empty)
}

/// One record, with the order of keys of `record_value` and without a copy of its data.
fn write_record(out: &mut Out, record: &Record) -> io::Result<()> {
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
