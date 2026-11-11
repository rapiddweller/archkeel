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
mod printable;
mod pyjson;
mod pyrepr;
mod records;
mod seam;
pub mod session;
mod shell;
mod stored;
mod validate;
mod view;

use archkeel_facts::Section;
use serde::Deserialize;
use serde_json::Value;

use crate::stored::Store;

/// Decode, validate and keep one reply in its typed form.
fn ingest(payload: &[u8], inflate_limit: u64) -> Result<Store, String> {
    let reply = decode::reply(payload, inflate_limit)?;
    validate::version(reply.protocol_version)?;
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

/// The canonical `architecture.json` of the parts of the shell.
fn write(request: Vec<u8>, store: &Store) -> Result<Vec<u8>, String> {
    let value = serde_json::from_slice::<Value>(&request).map_err(|error| error.to_string())?;
    drop(request);
    let (shell, model) = shell::frame(value, &canonical::CLASSIFIED_SECTIONS)?;
    canonical::encode(model, &shell, store)
}
