// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-store, core v1 stage 1 (AD-346, epic #880 target v2 WP4).
//!
//! The store reads one collector reply through the types of `archkeel-facts`, runs the generic
//! validation once and keeps the records. It gives the Python shell two outputs:
//!
//! 1. The read-set document (`seam`): the reply with only the record fields that a rule or a view
//!    reads. The Python check builds its facts from it and does not validate them again.
//! 2. The whole `architecture.json` 2.9 (`canonical`), byte-equal to the Python writer. Python
//!    passes its parts and names each stored record by its id.
//!
//! It also gives the receipt digest of a dependency proof (`pyrepr`) and the binding digest of a
//! member inventory proof (`inventory`), because they hash whole records that only the store holds.

#![deny(unreachable_pub)]

mod bindings;
mod canonical;
mod decode;
mod inventory;
mod pyjson;
mod pyrepr;
mod records;
mod registered;
mod seam;
pub mod session;
mod shell;
mod standard;
mod stored;
mod texts;
mod validate;
mod view;

use archkeel_facts::Section;
use serde::Deserialize;

pub use crate::standard::standard_library;
use crate::stored::Store;

/// A reply that the store decoded and validated once, for a library of the core (WP6, AD-363).
/// The records stay in their typed form; nothing outside the store can make one.
pub struct Ingested(Store);

impl Ingested {
    /// The typed reply: the model reads its records through the types of `archkeel-facts`.
    pub fn reply(&self) -> &archkeel_facts::envelope::Reply {
        self.0.reply()
    }
}

/// Decode and validate one compressed reply (protocol 8 or 9) for a library of the core.
pub fn ingest_reply(payload: &[u8], inflate_limit: u64) -> Result<Ingested, String> {
    ingest(payload, inflate_limit).map(Ingested)
}

/// Validate one typed reply of a collector that runs in the process of the core (AD-406). It is
/// the second front door of the same validation: `validated` runs every check that a decoded
/// reply gets, and nothing else makes an `Ingested`.
pub fn ingest_typed(reply: archkeel_facts::envelope::Reply) -> Result<Ingested, String> {
    validated(reply).map(Ingested)
}

/// Decode, validate and keep one reply in its typed form.
fn ingest(payload: &[u8], inflate_limit: u64) -> Result<Store, String> {
    validated(decode::reply(payload, inflate_limit)?)
}

/// The one validation of a reply after its decode: the version, the envelope, the registered
/// sets, the records and their bindings. Both front doors (`ingest_reply`, `ingest_typed`) end here.
fn validated(reply: archkeel_facts::envelope::Reply) -> Result<Store, String> {
    validate::version(reply.protocol_version)?;
    validate::invariants(&reply.facts)?;
    let names: Vec<&str> = reply.facts.sections.iter().map(Section::name).collect();
    validate::envelope(&reply.facts, &names)?;
    let places = records::records(&reply.facts, &validate::index(&reply.facts))?;
    Ok(Store::new(reply, places))
}

/// A bound item: the id of a stored entry, or the Python `repr` of an entry of the shell.
#[derive(Deserialize)]
#[serde(untagged)]
enum Bound {
    Stored(String),
    Written { repr: String },
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Binding {
    records: Vec<Bound>,
    evidence: Vec<Bound>,
}

/// The receipt digest of a dependency proof. The shell gives the items in sorted order.
fn bind(request: &[u8], store: &Store) -> Result<String, String> {
    let binding: Binding = serde_json::from_slice(request).map_err(|error| error.to_string())?;
    let records = binding
        .records
        .into_iter()
        .map(|item| match item {
            Bound::Stored(id) => pyrepr::record(&store.saved(&id)?),
            Bound::Written { repr } => Ok(repr),
        })
        .collect::<Result<Vec<_>, String>>()?;
    let evidence = binding
        .evidence
        .into_iter()
        .map(|item| match item {
            Bound::Stored(id) => Ok(pyrepr::evidence(store.evidence(&id)?)),
            Bound::Written { repr } => Ok(repr),
        })
        .collect::<Result<Vec<_>, String>>()?;
    Ok(pyrepr::binding_id(&records, &evidence))
}

/// The binding digest of a member inventory proof.
fn digest(request: &[u8], store: &Store) -> Result<String, String> {
    let value = serde_json::from_slice(request).map_err(|error| error.to_string())?;
    inventory::digest(value, store)
}

/// Bytes that a writer counts and drops: a frame is written once to count its length.
pub(crate) struct Count(pub(crate) u64);

impl std::io::Write for Count {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.0 += bytes.len() as u64;
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

/// The error of a frame that the stream ends before its length; it gets no answer.
pub(crate) fn truncated() -> std::io::Error {
    std::io::Error::new(std::io::ErrorKind::UnexpectedEof, "frame truncated")
}

/// Write the canonical `architecture.json` of the parts of the shell as one answer frame. It is
/// written twice, once to count its length for the frame header, and is never held. An error
/// before the header is the answer; an error after it ends the session. A frame that the stream
/// ends before its length gets no answer and ends the session.
fn write(
    request: &mut std::io::Take<impl std::io::Read>,
    store: &Store,
    output: &mut impl std::io::Write,
) -> Result<std::io::Result<()>, String> {
    let (shell, model) = shell::frame(&mut *request, &canonical::CLASSIFIED_SECTIONS)?;
    if request.limit() > 0 {
        return Ok(Err(truncated()));
    }
    let prepared = canonical::prepare(model, &shell, store)?;
    let mut count = Count(0);
    prepared.write_to(&mut count)?;
    Ok((|| {
        output.write_all(b"O")?;
        output.write_all(&count.0.to_be_bytes())?;
        prepared.write_to(output).map_err(std::io::Error::other)?;
        output.flush()
    })())
}
