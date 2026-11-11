// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed requests of the core (design WP6-0, section B). The shell owns Git and the file
//! system: it sends bytes, and the core reads no file.

use archkeel_model::{Section, Settings};

/// One request to the core.
#[derive(Debug)]
pub(crate) enum Request {
    /// The bytes of the root contract.
    Contract(Vec<u8>),
    /// The compressed collector reply (protocol 8 or 9), with the decompressed size limit.
    Ingest { reply: Vec<u8>, inflate_limit: u64 },
    /// What the shell read from the configuration and its profile table (AD-372).
    Settings(Settings),
    /// The rows of these sections (the dual run and the 2.9 writer).
    Sections(Vec<Section>),
    /// The decision of each rule of the contract.
    Rules,
    /// The report v2 payload.
    Report,
}

/// The sections of their names. A name outside the schema is refused by name.
pub(crate) fn sections(names: &[String]) -> Result<Vec<Section>, String> {
    names
        .iter()
        .map(|name| Section::of_name(name).ok_or_else(|| format!("unknown section {name}")))
        .collect()
}
