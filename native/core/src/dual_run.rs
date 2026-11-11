// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The engine command of the dual run (AD-360): one JSON request in, one engine frame out.
//!
//! The request carries the contract bytes and the collector reply (hex). The core sends them as
//! typed requests to the engine. The frame has no rule verdict and no section rows yet: each rule
//! and each requested section is in `unsupported` with its reason, and `self_test` shows what the
//! core read (the rule ids and kinds of the contract, the file count of the reply), so the harness
//! can prove the round trip.

use std::collections::BTreeMap;

use archkeel_contract::RuleKind;
use serde::{Deserialize, Serialize};

use crate::engine::{Answer, ContractState, Engine};
use crate::request::{self, Request};

const PROTOCOL: &str = "archkeel-dual-run-1";
/// The provenance of this build (`archkeel-build-support`).
const ENGINE: &str = concat!("archkeel-core ", env!("ARCHKEEL_CODE_DIGEST"));
/// The decompressed size limit of a reply in the dual run.
const INFLATE_LIMIT: u64 = 1 << 32;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DualRunRequest {
    protocol: String,
    case: String,
    // The shell fields: the core reads no file, so it uses only the bytes below.
    #[serde(rename = "root")]
    _root: String,
    #[serde(rename = "config")]
    _config: String,
    #[serde(rename = "baseline")]
    _baseline: Option<String>,
    #[serde(rename = "collector_argv")]
    _collector_argv: Option<Vec<String>>,
    #[serde(rename = "pinned")]
    _pinned: bool,
    contracts: BTreeMap<String, String>,
    reply: Option<ReplyBytes>,
    sections: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReplyBytes {
    hex: String,
}

#[derive(Serialize)]
struct Frame {
    engine: &'static str,
    /// The report v2 payload, or the reason that the core has none.
    report: String,
    rules: BTreeMap<String, [String; 2]>,
    unsupported: UnsupportedParts,
    self_test: SelfTest,
}

#[derive(Serialize)]
struct UnsupportedParts {
    /// The reason of each rule, or one reason for the whole contract.
    rules: RuleReasons,
    sections: BTreeMap<&'static str, String>,
}

#[derive(Serialize)]
#[serde(untagged)]
enum RuleReasons {
    Each(BTreeMap<String, String>),
    All(String),
}

#[derive(Serialize)]
struct SelfTest {
    contract: ContractCheck,
    reply: ReplyCheck,
}

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
enum ContractCheck {
    Rules(BTreeMap<String, RuleKind>),
    Unsupported(String),
    Refused(String),
}

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
enum ReplyCheck {
    Files(usize),
    Refused(String),
    Absent(String),
}

/// The frame of one request. An error is a request that the core cannot read.
pub(crate) fn answer(input: &[u8]) -> Result<Vec<u8>, String> {
    let request: DualRunRequest =
        serde_json::from_slice(input).map_err(|error| format!("invalid request: {error}"))?;
    if request.protocol != PROTOCOL {
        return Err(format!("unknown protocol {}", request.protocol));
    }
    let [(_, contract)] =
        <[(String, String); 1]>::try_from(request.contracts.into_iter().collect::<Vec<_>>())
            .map_err(|found| {
                format!(
                    "{}: one root contract expected, {} found",
                    request.case,
                    found.len()
                )
            })?;
    let sections = request::sections(&request.sections)?;
    let mut engine = Engine::default();
    let contract = match engine.answer(Request::Contract(contract.into_bytes())) {
        Answer::Contract(state) => state,
        other => ContractState::Refused(format!("unexpected answer {other:?}")),
    };
    let reply = match request.reply {
        None => ReplyCheck::Absent("the request carries no collector reply".to_owned()),
        Some(bytes) => match engine.answer(Request::Ingest {
            reply: hex(&bytes.hex)?,
            inflate_limit: INFLATE_LIMIT,
        }) {
            Answer::Ingested(files) => ReplyCheck::Files(files),
            Answer::ReplyRefused(message) => ReplyCheck::Refused(message),
            other => ReplyCheck::Refused(format!("unexpected answer {other:?}")),
        },
    };
    let rows = match engine.answer(Request::Sections(sections)) {
        Answer::Sections(rows) => rows,
        _ => Vec::new(),
    };
    let rules = match &contract {
        ContractState::Parsed(_) => RuleReasons::Each(
            engine
                .rule_reasons()
                .into_iter()
                .map(|(id, reason)| (id, reason.to_string()))
                .collect(),
        ),
        ContractState::Unsupported(reason) => RuleReasons::All(reason.to_string()),
        ContractState::Refused(message) => RuleReasons::All(format!("refused: {message}")),
    };
    let report = match engine.answer(Request::Report) {
        Answer::Unsupported(reason) => reason.to_string(),
        other => format!("unexpected answer {other:?}"),
    };
    let frame = Frame {
        engine: ENGINE,
        report,
        rules: BTreeMap::new(),
        unsupported: UnsupportedParts {
            rules,
            sections: rows
                .into_iter()
                .map(|(section, reason)| (section.name(), reason.to_string()))
                .collect(),
        },
        self_test: SelfTest {
            contract: match contract {
                ContractState::Parsed(rules) => ContractCheck::Rules(rules),
                ContractState::Unsupported(reason) => {
                    ContractCheck::Unsupported(reason.to_string())
                }
                ContractState::Refused(message) => ContractCheck::Refused(message),
            },
            reply,
        },
    };
    serde_json::to_vec(&frame).map_err(|error| error.to_string())
}

/// The bytes of a hex text.
fn hex(text: &str) -> Result<Vec<u8>, String> {
    let digits = text.as_bytes();
    if !digits.len().is_multiple_of(2) {
        return Err("the reply hex has an odd length".to_owned());
    }
    digits
        .chunks(2)
        .map(|pair| {
            let high = (pair[0] as char).to_digit(16);
            let low = (pair[1] as char).to_digit(16);
            match (high, low) {
                (Some(high), Some(low)) => u8::try_from(high * 16 + low)
                    .map_err(|_| "the reply hex is not a byte".to_owned()),
                _ => Err("the reply hex has a character that is not a hex digit".to_owned()),
            }
        })
        .collect()
}

#[cfg(test)]
#[path = "dual_run_tests.rs"]
mod tests;
