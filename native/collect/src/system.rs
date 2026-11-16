// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The system document of a repository (AD-616, the first slice of the system contract of
//! AD-522): a title and parts, each with the configuration of one scan. The core runs one scan for
//! each part and joins their frames. A part names no language; its configuration does.

use serde_json::{Map, Value};

use crate::refusal::{refused, Refusal};
use crate::repository::{safe_config, Over, Root, MAX_CONFIG_BYTES};

/// The one version of the system document that the core reads.
const VERSION: &str = "archkeel-system-contract-1";

/// A system document: its title, its repository path and bytes, and its parts.
pub struct System {
    /// The title of the system.
    pub title: String,
    /// The repository path of the document and its bytes.
    pub document: (String, Vec<u8>),
    /// The parts, in the order of the document.
    pub parts: Vec<SystemPart>,
}

/// One part of a system: the scan of one configuration.
pub struct SystemPart {
    /// The id of the part, unique in the document.
    pub id: String,
    /// The title of the part.
    pub title: String,
    /// The repository path of the scan configuration of the part.
    pub config: String,
}

/// The keys of an object of the document, exactly: a key that the core does not read refuses it.
fn object<'a>(
    value: &'a Value,
    keys: &[&str],
    what: &str,
) -> Result<&'a Map<String, Value>, Refusal> {
    let map = value
        .as_object()
        .ok_or_else(|| refused("system", format!("{what} is no object")))?;
    let mut found: Vec<&str> = map.keys().map(String::as_str).collect();
    let mut wanted = keys.to_vec();
    found.sort_unstable();
    wanted.sort_unstable();
    if found == wanted {
        Ok(map)
    } else {
        Err(refused(
            "system",
            format!("{what} has the keys {found:?}, not {wanted:?}"),
        ))
    }
}

fn text(map: &Map<String, Value>, key: &str, what: &str) -> Result<String, Refusal> {
    map.get(key)
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| refused("system", format!("{what}.{key} is no text")))
}

/// The system document at `path` below `root`.
pub(crate) fn read(root: &Root, path: &str) -> Result<Option<System>, Refusal> {
    let bytes = match root.read(path, MAX_CONFIG_BYTES) {
        Ok(Some((_, bytes))) => bytes,
        Ok(None) => return Err(refused("system", format!("cannot read {path}"))),
        Err(Over(_)) => return Err(refused("system", format!("{path} is too large"))),
    };
    let value: Value = serde_json::from_slice(&bytes)
        .map_err(|error| refused("system", format!("{path}: {error}")))?;
    let keys = ["schema_version", "kind", "title", "parts", "rules"];
    let document = object(&value, &keys, path)?;
    let kind = (
        text(document, "schema_version", "system")?,
        text(document, "kind", "system")?,
    );
    if kind != (VERSION.to_owned(), "system".to_owned()) {
        return Err(refused(
            "system",
            format!("{path} is no {VERSION} document"),
        ));
    }
    let rules = document.get("rules").and_then(Value::as_array);
    if !rules.is_some_and(Vec::is_empty) {
        let why = "unsupported: a rule between parts (no rule kind reads two replies yet)";
        return Err(refused("system", why));
    }
    let listed = document
        .get("parts")
        .and_then(Value::as_array)
        .filter(|p| !p.is_empty());
    let listed = listed.ok_or_else(|| refused("system", "the system document names no part"))?;
    let mut parts = Vec::new();
    for item in listed {
        let part = object(item, &["id", "title", "config"], "a part")?;
        let (id, config) = (text(part, "id", "part")?, text(part, "config", "part")?);
        safe_config(&config)?;
        if config.ends_with(".json") {
            return Err(refused("system", format!("the part {id} names a system")));
        }
        if parts.iter().any(|seen: &SystemPart| seen.id == id) {
            return Err(refused("system", format!("two parts have the id {id}")));
        }
        let title = text(part, "title", "part")?;
        parts.push(SystemPart { id, title, config });
    }
    Ok(Some(System {
        title: text(document, "title", "system")?,
        document: (path.to_owned(), bytes),
        parts,
    }))
}
