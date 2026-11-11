// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The engine command of the dual run (AD-360): one JSON request in, one engine frame out.
//!
//! The request carries the contract bytes and the collector reply (hex). The core sends them as
//! typed requests to the engine. The frame has the status of each decided rule (`rules`) and the
//! rows of each ported section (`sections`). Each other rule and section is in `unsupported` with
//! its reason, and `self_test` shows what the core read (the rule ids and kinds of the contract,
//! the file count of the reply), so the harness can prove the round trip.

use std::collections::BTreeMap;

use archkeel_contract::RuleKind;
use archkeel_model::{Section, Settings};
use serde::{Deserialize, Serialize};

use crate::contract::ContractState;
use crate::engine::{Answer, Engine};
use crate::ingest::ReplyState;
use crate::request::{self, Request};
use crate::rules::RuleAnswer;
use archkeel_model::{Reason, Unsupported};

/// Version 2 adds the settings of the shell: `namespace` and `standard_library` (AD-372).
const PROTOCOL: &str = "archkeel-dual-run-2";
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
    /// A baseline changes what a run reports; no slice reads it yet, so it is refused by name.
    baseline: Option<String>,
    #[serde(rename = "collector_argv")]
    _collector_argv: Option<Vec<String>>,
    #[serde(rename = "pinned")]
    _pinned: bool,
    contracts: BTreeMap<String, String>,
    reply: Option<ReplyBytes>,
    sections: Vec<String>,
    /// The namespace of the configuration, which the shell reads (AD-372).
    namespace: String,
    /// The top-level names of the standard library of the profile of the reply (AD-372).
    standard_library: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReplyBytes {
    hex: String,
}

#[derive(Serialize)]
struct Frame {
    engine: &'static str,
    rules: BTreeMap<String, [String; 2]>,
    sections: BTreeMap<&'static str, Vec<serde_json::Value>>,
    /// The edge rows without the ranks of S3, when the request names `dependency_edges`.
    #[serde(skip_serializing_if = "Option::is_none")]
    edges: Option<Vec<serde_json::Value>>,
    unsupported: UnsupportedParts,
    self_test: SelfTest,
}

#[derive(Serialize)]
struct UnsupportedParts {
    /// The reason of each rule, or one reason for the whole contract.
    rules: RuleReasons,
    sections: BTreeMap<&'static str, String>,
    /// The reason that the core has no report v2 payload (slice 0d).
    report: Option<String>,
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

/// The answer of the core: the frame bytes, and whether the frame names a part that is
/// unsupported or refused. A caller never sees a frame without verdicts as a plain success.
pub(crate) struct Answered {
    pub(crate) frame: Vec<u8>,
    pub(crate) names_a_gap: bool,
}

/// The frame of one request. An error is a request that the core cannot read.
pub(crate) fn answer(input: &[u8]) -> Result<Answered, String> {
    let request: DualRunRequest =
        serde_json::from_slice(input).map_err(|error| format!("invalid request: {error}"))?;
    if request.protocol != PROTOCOL {
        return Err(format!("unknown protocol {}", request.protocol));
    }
    let [(path, contract)] =
        <[(String, String); 1]>::try_from(request.contracts.into_iter().collect::<Vec<_>>())
            .map_err(|found| {
                let count = found.len();
                format!(
                    "{}: one root contract expected, {count} found",
                    request.case
                )
            })?;
    let sections = request::sections(&request.sections)?;
    let edges_asked = sections.contains(&Section::DependencyEdges);
    let mut engine = Engine::default();
    engine.answer(Request::Settings(Settings::new(
        request.namespace,
        request.standard_library,
    )));
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
            Answer::Reply(ReplyState::Ingested(files)) => ReplyCheck::Files(files),
            Answer::Reply(ReplyState::Refused(message)) => ReplyCheck::Refused(message),
            other => ReplyCheck::Refused(format!("unexpected answer {other:?}")),
        },
    };
    let rows = match engine.answer(Request::Sections(sections)) {
        Answer::Sections(rows) => rows,
        _ => Vec::new(),
    };
    // The report holds a reason until slice 0d writes the payload, so it is a named gap.
    let report: Result<(), String> = match engine.answer(Request::Report) {
        Answer::Report(reason) => Err(reason.to_string()),
        other => Err(format!("unexpected answer {other:?}")),
    };
    let mut decided = match engine.answer(Request::Rules) {
        Answer::Rules(answer) => answer,
        _ => RuleAnswer::default(),
    };
    let baseline = request
        .baseline
        .is_some()
        .then_some(Reason::Unsupported(Unsupported::Baseline));
    let rules = match (&contract, baseline) {
        (_, Some(reason)) => {
            decided.decided.clear();
            RuleReasons::All(reason.to_string())
        }
        (contract, None) => match contract {
            ContractState::Parsed(_) => RuleReasons::Each(
                crate::contract::uml_reason(engine.contract(), &path)
                    .into_iter()
                    .chain(decided.reasons)
                    .map(|(id, reason)| (id, reason.to_string()))
                    .collect(),
            ),
            ContractState::Unsupported(reason) => RuleReasons::All(reason.to_string()),
            ContractState::Refused(message) => RuleReasons::All(format!("refused: {message}")),
        },
    };
    let edges = edges_asked
        .then(|| engine.reply_and_settings())
        .flatten()
        .map(|(reply, settings)| crate::edges::rows(reply, settings));
    let (rows, sections) = crate::sections::split(rows);
    let names_a_gap = report.is_err()
        || !matches!(&rules, RuleReasons::Each(each) if each.is_empty())
        || !sections.is_empty()
        || !matches!(reply, ReplyCheck::Files(_))
        || !matches!(contract, ContractState::Parsed(_));
    let frame = Frame {
        engine: ENGINE,
        rules: decided.decided,
        sections: rows,
        edges,
        unsupported: UnsupportedParts {
            rules,
            sections,
            report: report.err(),
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
    let frame = serde_json::to_vec(&frame).map_err(|error| error.to_string())?;
    Ok(Answered { frame, names_a_gap })
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
