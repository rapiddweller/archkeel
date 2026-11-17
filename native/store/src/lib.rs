// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-store (AD-346, epic #880 target v2 WP4).
//!
//! The store reads one collector reply through the types of `archkeel-facts`, runs the generic
//! validation once and keeps the records for the model of the core (`ingest_reply`,
//! `ingest_typed`). It also reads the pinned standard library by the key that a reply names.
//!
//! The process, the read-set document and the writer of `architecture.json` for the Python shell
//! are deleted with the Python engine (AD-432).

#![deny(unreachable_pub)]

mod bindings;
mod dart;
mod decode;
mod features;
mod python;
mod record_identity;
mod records;
mod standard;
mod stored;
mod validate;
mod validation;
mod view;

#[cfg(test)]
mod construct_tests;

#[cfg(test)]
mod construct_consistency_tests;

use archkeel_facts::Section;

pub use crate::standard::{
    sdk_libraries, standard_library, standard_library_at, standard_library_everywhere,
};
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

/// Decode and validate one compressed reply (protocol 11) for a library of the core.
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
    validate::invariants(&reply.facts)?;
    let names: Vec<&str> = reply.facts.sections.iter().map(Section::name).collect();
    validate::envelope(&reply.facts, &names)?;
    validation::check(&reply.facts)?;
    records::records(&reply.facts, &validate::index(&reply.facts))?;
    Ok(Store::new(reply))
}
