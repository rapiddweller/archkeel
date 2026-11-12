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
use archkeel_model::{Producer, Settings};
use serde::{Deserialize, Serialize};

use crate::contract::{ContractInput, ContractState, InsideFile};
use crate::engine::{Answer, Engine};
use crate::ingest::ReplyState;
use crate::request::{self, Request};
use crate::rules::RuleAnswer;
use archkeel_model::{Reason, Unsupported};

/// Version 2 adds the settings of the shell: `namespace` and `standard_library` (AD-372).
/// Version 3 adds `insides`: the inside contracts that the shell read (AD-379).
/// Version 4 adds `roots`: the scan roots of the configuration (AD-384).
const PROTOCOL: &str = "archkeel-dual-run-4";
/// The provenance of this build (`archkeel-build-support`).
const ENGINE: &str = concat!("archkeel-core ", env!("ARCHKEEL_CODE_DIGEST"));
/// The longest `collector_argv` that a test request can name (AD-378 point 4: the producer of the
/// dual-run request is the word of a test caller, not evidence).
const ARGV_LIMIT: usize = 64;
/// The decompressed size limit of a reply in the dual run.
const INFLATE_LIMIT: u64 = 1 << 32;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct DualRunRequest {
    // Checked before through `Head`.
    #[serde(rename = "protocol")]
    _protocol: String,
    case: String,
    // The shell fields: the core reads no file, so it uses only the bytes below.
    #[serde(rename = "root")]
    _root: String,
    #[serde(rename = "config")]
    _config: String,
    /// A baseline changes what a run reports; no slice reads it yet, so it is refused by name.
    baseline: Option<String>,
    /// The command of an external collector; `None` for the bundled collector. With `pinned`,
    /// the host trusts the reply of an external collector (AD-344, AD-378).
    collector_argv: Option<Vec<String>>,
    pinned: bool,
    contracts: BTreeMap<String, String>,
    reply: Option<ReplyBytes>,
    sections: Vec<String>,
    /// The namespace of the configuration, which the shell reads (AD-372).
    namespace: String,
    /// The profile of the reply as the shell read it, and its standard library (AD-372).
    profile: String,
    standard_library: Vec<String>,
    /// The inside contracts that the shell read for the paths of an earlier frame (AD-379).
    insides: Vec<InsideJson>,
    /// The scan roots of the configuration, which the shell reads (AD-384). The model binds
    /// them to the scope of the reply, so they are not the word of the caller.
    roots: Vec<String>,
}

/// One inside contract of a request: the reference of the mount, the repository-relative path
/// that the shell resolved it to, and the bytes in hex.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct InsideJson {
    reference: String,
    identity: String,
    hex: String,
}

/// The protocol of a request, read before the fields that the protocol defines.
#[derive(Deserialize)]
struct Head {
    protocol: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReplyBytes {
    hex: String,
}

#[derive(Serialize)]
struct Frame {
    engine: &'static str,
    /// The status that the rows give (AD-361 point 4, `status.rs`).
    status: &'static str,
    rules: BTreeMap<String, [String; 2]>,
    /// The explaining row of each decided rule that is not PASS: the reason of an UNKNOWN rule
    /// and the number of violations of a FAIL rule (AD-361 point 5).
    explained: BTreeMap<String, String>,
    violations: BTreeMap<String, usize>,
    /// Each PASS rule that the reference engine gives UNKNOWN for a kept pair gap, with the
    /// reason that the core decides it (AD-384 point 4).
    beyond: BTreeMap<String, String>,
    /// Why the scope of the run is not complete, or `complete` (L-35b).
    scope: String,
    sections: BTreeMap<&'static str, Vec<serde_json::Value>>,
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
    /// The repository paths of the inside contracts that the shell must still send.
    Missing(Vec<String>),
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
    let head: Head =
        serde_json::from_slice(input).map_err(|error| format!("invalid request: {error}"))?;
    if head.protocol != PROTOCOL {
        return Err(format!("unknown protocol {}", head.protocol));
    }
    let request: DualRunRequest =
        serde_json::from_slice(input).map_err(|error| format!("invalid request: {error}"))?;
    bounded(&request)?;
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
    let mut engine = Engine::default();
    let producer = producer(request.collector_argv.as_ref(), request.pinned);
    let settings = Settings::new(request.namespace, request.profile, request.standard_library)
        .with_producer(producer)
        .with_contract_source(&path, contract.as_bytes());
    // No roots narrow the run: a receipt that needs them names `Part::ScanRoots`.
    let settings = if request.roots.is_empty() {
        settings
    } else {
        settings.with_roots(request.roots)
    };
    engine.answer(Request::Settings(settings));
    let input = ContractInput {
        path,
        bytes: contract.into_bytes(),
        insides: insides(request.insides)?,
    };
    let path = input.path.clone();
    let contract = match engine.answer(Request::Contract(input)) {
        Answer::Contract(state) => state,
        other => ContractState::Refused(format!("unexpected answer {other:?}")),
    };
    let reply = ingest(&mut engine, request.reply)?;
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
    let rules = rule_reasons(
        &contract,
        request.baseline.is_some(),
        &engine,
        &path,
        &mut decided,
    );
    let (rows, sections) = crate::sections::split(rows);
    let names_a_gap = report.is_err()
        || !matches!(&rules, RuleReasons::Each(each) if each.is_empty())
        || !sections.is_empty()
        || !matches!(reply, ReplyCheck::Files(_))
        || !matches!(contract, ContractState::Parsed(_));
    if let Some(problem) = crate::status::unexplained(&decided) {
        return Err(format!(
            "{}: an inconsistent frame: {problem}",
            request.case
        ));
    }
    // A section without rows is a gap of the sections, not of the rules: it changes no status.
    let named = names_a_part(&rules, &reply, &contract);
    let frame = Frame {
        engine: ENGINE,
        status: crate::status::status(&decided.decided, named, decided.scope.is_none()),
        scope: decided
            .scope
            .clone()
            .unwrap_or_else(|| "complete".to_owned()),
        explained: decided.explained,
        violations: decided.violations,
        beyond: decided.beyond,
        rules: decided.decided,
        sections: rows,
        unsupported: UnsupportedParts {
            rules,
            sections,
            report: report.err(),
        },
        self_test: SelfTest {
            contract: match contract {
                ContractState::Parsed(rules) => ContractCheck::Rules(rules),
                ContractState::Missing(paths) => ContractCheck::Missing(paths),
                ContractState::Refused(message) => ContractCheck::Refused(message),
            },
            reply,
        },
    };
    let frame = serde_json::to_vec(&frame).map_err(|error| error.to_string())?;
    Ok(Answered { frame, names_a_gap })
}

/// The request refused by name when its `collector_argv` is longer than the limit.
fn bounded(request: &DualRunRequest) -> Result<(), String> {
    match &request.collector_argv {
        Some(argv) if argv.len() > ARGV_LIMIT => Err(format!(
            "{}: collector_argv has more than {ARGV_LIMIT} entries",
            request.case
        )),
        _ => Ok(()),
    }
}

/// The producer of the reply: the bundled collector, or an external command that the host pins,
/// is trusted (`cli/observe.py` `observer_for`). The dual-run request is a test protocol: these
/// fields are the word of the caller, not evidence. The request of M1 must not take them from a
/// caller: the shell starts the pinned collector, checks its digest and fills the producer and
/// the standard library from its own profile table (AD-378 point 4).
fn producer(collector_argv: Option<&Vec<String>>, pinned: bool) -> Producer {
    if collector_argv.is_none() || pinned {
        Producer::Trusted
    } else {
        Producer::External
    }
}

/// The reasons of the rules without a decision. A baseline names the whole contract and keeps no
/// decision; a contract that the core cannot use names itself.
fn rule_reasons(
    contract: &ContractState,
    baseline: bool,
    engine: &Engine,
    path: &str,
    decided: &mut RuleAnswer,
) -> RuleReasons {
    if baseline {
        let scope = decided.scope.take();
        *decided = RuleAnswer {
            scope,
            ..RuleAnswer::default()
        };
        return RuleReasons::All(Reason::Unsupported(Unsupported::Baseline).to_string());
    }
    match contract {
        ContractState::Parsed(_) => RuleReasons::Each(
            crate::contract::uml_reason(engine.usable(), path)
                .into_iter()
                .chain(std::mem::take(&mut decided.reasons))
                .map(|(id, reason)| (id, reason.to_string()))
                .collect(),
        ),
        ContractState::Missing(paths) => RuleReasons::All(crate::contract::missing_reason(paths)),
        ContractState::Refused(message) => RuleReasons::All(format!("refused: {message}")),
    }
}

/// True when the frame names a rule reason (an inside rule of a tree among them, AD-379), a
/// refused reply or a contract that the core cannot use: then the status is never PASS.
fn names_a_part(rules: &RuleReasons, reply: &ReplyCheck, contract: &ContractState) -> bool {
    !matches!(rules, RuleReasons::Each(each) if each.is_empty())
        || !matches!(reply, ReplyCheck::Files(_))
        || !matches!(contract, ContractState::Parsed(_))
}

/// What the engine knows of the reply of the request, after it ingests the reply.
fn ingest(engine: &mut Engine, reply: Option<ReplyBytes>) -> Result<ReplyCheck, String> {
    let Some(bytes) = reply else {
        let absent = "the request carries no collector reply".to_owned();
        return Ok(ReplyCheck::Absent(absent));
    };
    Ok(
        match engine.answer(Request::Ingest {
            reply: hex(&bytes.hex)?,
            inflate_limit: INFLATE_LIMIT,
        }) {
            Answer::Reply(ReplyState::Ingested(files)) => ReplyCheck::Files(files),
            Answer::Reply(ReplyState::Refused(message)) => ReplyCheck::Refused(message),
            other => ReplyCheck::Refused(format!("unexpected answer {other:?}")),
        },
    )
}

/// The inside contracts of the request, decoded. The whole request is already read, so the
/// bounds of the count and the size are checked in `contract::answer` and give a named refusal
/// (exit 3), not an unreadable request (AD-379).
fn insides(files: Vec<InsideJson>) -> Result<Vec<InsideFile>, String> {
    files
        .into_iter()
        .map(|file| {
            Ok(InsideFile {
                bytes: hex(&file.hex)?,
                reference: file.reference,
                identity: file.identity,
            })
        })
        .collect()
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

#[cfg(test)]
#[path = "tree_tests.rs"]
mod tree_tests;
