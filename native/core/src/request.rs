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

/// The sections of their names. A name outside the schema and a repeated name are refused by
/// name before any row is built: a repeated name would build the same rows again (AD-374).
pub(crate) fn sections(names: &[String]) -> Result<Vec<Section>, String> {
    let mut found: Vec<Section> = Vec::with_capacity(names.len());
    for name in names {
        let section = Section::of_name(name).ok_or_else(|| format!("unknown section {name}"))?;
        if found.contains(&section) {
            return Err(format!(
                "repeated section {name}: name each section one time"
            ));
        }
        found.push(section);
    }
    Ok(found)
}
