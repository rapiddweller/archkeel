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
    /// The interfaces between the parts, in the order of the document.
    pub interfaces: Vec<SystemInterface>,
}

/// One interface between two parts: what crosses, and the schema file that states it.
pub struct SystemInterface {
    /// The id of the interface, unique in the document.
    pub id: String,
    /// The id of the part that uses the interface.
    pub source: String,
    /// The id of the part that provides it.
    pub target: String,
    /// What crosses, in one line.
    pub title: String,
    /// The repository path of the schema of what crosses; the file exists.
    pub schema: String,
}

/// One part of a system: the scan of one configuration, and what the part is for.
pub struct SystemPart {
    /// The id of the part, unique in the document.
    pub id: String,
    /// The title of the part.
    pub title: String,
    /// The repository path of the scan configuration of the part.
    pub config: String,
    /// What the part is responsible for; each part states at least one line.
    pub responsibilities: Vec<String>,
    /// What the part is not responsible for; at least one line.
    pub forbidden_responsibilities: Vec<String>,
    /// What the part provides to the other parts; at least one line.
    pub provides: Vec<String>,
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

/// A list of lines: at least one, each a text. A part with no written line is refused.
fn lines(map: &Map<String, Value>, key: &str, what: &str) -> Result<Vec<String>, Refusal> {
    let found: Option<Vec<String>> = map.get(key).and_then(Value::as_array).and_then(|list| {
        list.iter()
            .map(|v| v.as_str().filter(|t| !t.is_empty()).map(str::to_owned))
            .collect()
    });
    found
        .filter(|list| !list.is_empty())
        .ok_or_else(|| refused("system", format!("{what}.{key} is no list of texts")))
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
    let keys = [
        "schema_version",
        "kind",
        "title",
        "parts",
        "interfaces",
        "rules",
    ];
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
        let keys = [
            "id",
            "title",
            "config",
            "responsibilities",
            "forbidden_responsibilities",
            "provides",
        ];
        let part = object(item, &keys, "a part")?;
        let (id, config) = (text(part, "id", "part")?, text(part, "config", "part")?);
        safe_config(&config)?;
        if config.ends_with(".json") {
            return Err(refused("system", format!("the part {id} names a system")));
        }
        if parts.iter().any(|seen: &SystemPart| seen.id == id) {
            return Err(refused("system", format!("two parts have the id {id}")));
        }
        parts.push(SystemPart {
            id,
            title: text(part, "title", "part")?,
            config,
            responsibilities: lines(part, "responsibilities", "part")?,
            forbidden_responsibilities: lines(part, "forbidden_responsibilities", "part")?,
            provides: lines(part, "provides", "part")?,
        });
    }
    let interfaces = interfaces(root, document, &parts)?;
    Ok(Some(System {
        title: text(document, "title", "system")?,
        document: (path.to_owned(), bytes),
        parts,
        interfaces,
    }))
}

/// The interfaces of the document: each joins two parts and names a schema file that exists.
fn interfaces(
    root: &Root,
    document: &Map<String, Value>,
    parts: &[SystemPart],
) -> Result<Vec<SystemInterface>, Refusal> {
    let listed = document.get("interfaces").and_then(Value::as_array);
    let listed = listed.ok_or_else(|| refused("system", "system.interfaces is no list"))?;
    let mut found: Vec<SystemInterface> = Vec::new();
    for item in listed {
        let keys = ["id", "source", "target", "title", "schema"];
        let map = object(item, &keys, "an interface")?;
        let interface = SystemInterface {
            id: text(map, "id", "interface")?,
            source: text(map, "source", "interface")?,
            target: text(map, "target", "interface")?,
            title: text(map, "title", "interface")?,
            schema: text(map, "schema", "interface")?,
        };
        let id = &interface.id;
        if found.iter().any(|seen| seen.id == *id) {
            return Err(refused(
                "system",
                format!("two interfaces have the id {id}"),
            ));
        }
        for end in [&interface.source, &interface.target] {
            if !parts.iter().any(|part| part.id == *end) {
                return Err(refused(
                    "system",
                    format!("the interface {id} names no part {end}"),
                ));
            }
        }
        if interface.source == interface.target {
            return Err(refused(
                "system",
                format!("the interface {id} joins a part to itself"),
            ));
        }
        safe_config(&interface.schema)?;
        let exists = matches!(root.read(&interface.schema, MAX_CONFIG_BYTES), Ok(Some(_)));
        if !exists {
            let path = &interface.schema;
            return Err(refused(
                "system",
                format!("the schema {path} of the interface {id} is no file"),
            ));
        }
        found.push(interface);
    }
    Ok(found)
}
