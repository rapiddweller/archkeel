// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The payload as data and its canonical bytes (AD-361 point 9).
//!
//! A `Payload` is what the bytes say; it is not checked. Only `Report` (built or checked) carries
//! the promise of the status rule, so the type and `encode` are private to the crate (its `pub`
//! fields reach no other crate): bytes leave only through `Report::encode` (#1073 item 6,
//! AD-381). The field order is the canonical key order: the `required`
//! list of the schema, then the optional `fields` and `params` after `carriers`.
//!
//! The writer is the compact writer of `serde_json`: no whitespace, UTF-8, and a string escapes
//! only `"`, `\` and U+0000 to U+001F (`\b \f \n \r \t`, else `\u00xx` with lowercase hex). A
//! unit test pins each escape, so a change of `serde_json` that changes the bytes fails.

use serde::{Deserialize, Serialize};

use crate::head::{Component, GapRow, RuleResult, Run, Summary, TrendPoint};
use crate::tables::{
    Carriers, Crossings, Edges, Fields, Findings, Id, Measures, Nodes, Params, Permissions, StrId,
    Units, Unknowns, Variants, Violations,
};

/// The schema version that this crate writes.
pub const SCHEMA_VERSION: &str = "2.0.0";
/// The byte budget of a payload (AD-361 point 11).
pub const MAX_BYTES: u64 = 8_000_000;

/// The report v2 payload, as the bytes say.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Payload {
    pub schema_version: String,
    pub run: Run,
    pub summary: Summary,
    pub rules: Vec<RuleResult>,
    pub gaps: Vec<GapRow>,
    pub components: Vec<Component>,
    pub trend: Vec<TrendPoint>,
    pub strings: Vec<String>,
    pub nodes: Nodes,
    pub measures: Measures,
    pub units: Units,
    pub variants: Variants,
    pub edges: Edges,
    pub via: Vec<Id>,
    pub crossings: Crossings,
    pub permissions: Permissions,
    pub violations: Violations,
    pub violation_rules: Vec<StrId>,
    pub violation_subjects: Vec<StrId>,
    pub violation_evidence: Vec<StrId>,
    pub unknowns: Unknowns,
    pub findings: Findings,
    pub carriers: Carriers,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fields: Option<Fields>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub params: Option<Params>,
}

/// Why bytes are no payload.
#[derive(Debug)]
pub enum DecodeError {
    /// The bytes are no JSON of the payload shape: a missing, unknown or repeated key, a wrong
    /// type or a negative count.
    Shape(serde_json::Error),
    /// The bytes decode, but they are not the canonical bytes of what they hold.
    NotCanonical,
}

impl std::fmt::Display for DecodeError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DecodeError::Shape(error) => write!(formatter, "not a report v2 payload: {error}"),
            DecodeError::NotCanonical => {
                formatter.write_str("the payload bytes are not canonical (AD-361 point 9)")
            }
        }
    }
}

impl Payload {
    /// The canonical bytes: compact JSON in schema key order and one trailing newline.
    pub(crate) fn encode(&self) -> Result<Vec<u8>, serde_json::Error> {
        let mut bytes = serde_json::to_vec(self)?;
        bytes.push(b'\n');
        Ok(bytes)
    }

    /// Read canonical bytes. Bytes that decode but differ from their own encoding are refused:
    /// another key order, whitespace, another escape, or a missing nullable key.
    pub(crate) fn decode(bytes: &[u8]) -> Result<Payload, DecodeError> {
        let payload: Payload = serde_json::from_slice(bytes).map_err(DecodeError::Shape)?;
        match payload.encode() {
            Ok(again) if again == bytes => Ok(payload),
            _ => Err(DecodeError::NotCanonical),
        }
    }
}
