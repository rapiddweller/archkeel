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
use archkeel_store::Ingested;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};

use crate::contract::{ContractInput, ContractState, InsideFile};
use crate::engine::{Answer, Engine};
use crate::ingest::ReplyState;
use crate::request::{self, Request};
use archkeel_model::{Reason, Unsupported};
use archkeel_report::Named;

#[path = "scan_refusal.rs"]
mod scan_refusal;
pub(crate) use scan_refusal::refused_scan;

/// Version 2 adds the settings of the shell: `namespace` and `standard_library` (AD-372).
/// Version 3 adds `insides`: the inside contracts that the shell read (AD-379).
/// Version 4 adds `roots`: the scan roots of the configuration (AD-384).
/// Version 5 removes `pinned`: the core takes no trust statement from a request (AD-388).
const PROTOCOL: &str = "archkeel-dual-run-5";
/// The provenance of this build (`archkeel-build-support`).
const ENGINE: &str = concat!("archkeel-core ", env!("ARCHKEEL_CODE_DIGEST"));
/// The longest `collector_argv` that a test request can name (AD-378 point 4: the producer of the
/// dual-run request is the word of a test caller, not evidence).
const ARGV_LIMIT: usize = 64;
/// The decompressed size limit of a reply in the dual run.
pub(crate) const INFLATE_LIMIT: u64 = 1 << 32;

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
    /// A baseline changes what a run reports: `Run::baseline`.
    baseline: Option<String>,
    /// The command of an external collector; `None` for the bundled collector. The core cannot
    /// verify a pin of an external collector, so it never trusts one (AD-388). A request with a
    /// `pinned` field is refused as an unknown field.
    collector_argv: Option<Vec<String>>,
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
pub(crate) struct InsideJson {
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
pub(crate) struct ReplyBytes {
    pub(crate) hex: String,
}

/// The parts that the core adds to the engine frame. The status, the rule verdicts, their
/// explaining rows, `beyond`, the scope and `unsupported.rules` come only from the `Ruling` of
/// the report, which writes the frame and refuses a part with one of its keys (AD-388, AD-384
/// point 4).
#[derive(Serialize)]
struct Parts {
    engine: &'static str,
    sections: BTreeMap<&'static str, Vec<serde_json::Value>>,
    unsupported: UnsupportedParts,
    self_test: SelfTest,
    locations: BTreeMap<String, Location>,
}

#[derive(Serialize)]
struct Location {
    path: String,
    line: i64,
}

#[derive(Serialize)]
struct UnsupportedParts {
    sections: BTreeMap<&'static str, String>,
    /// The reason that the core has no report v2 payload (slice 0d).
    report: Option<String>,
}

#[derive(Serialize)]
struct SelfTest {
    contract: ContractCheck,
    reply: ReplyCheck,
    /// The scan request only (AD-406): the request that the core derived, or why it has none.
    #[serde(skip_serializing_if = "Option::is_none")]
    collect: Option<serde_json::Value>,
}

#[derive(Serialize)]
#[serde(rename_all = "snake_case")]
enum ContractCheck {
    Rules(BTreeMap<String, RuleKind>),
    /// The repository paths of the inside contracts that the shell must still send.
    Missing(Vec<String>),
    Refused(String),
    NotRead(String),
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

/// A request of one protocol: the protocol is read before the fields that it defines. An error
/// is a request that the core cannot read.
pub(crate) fn decode<T: DeserializeOwned>(input: &[u8], protocol: &str) -> Result<T, String> {
    let head: Head =
        serde_json::from_slice(input).map_err(|error| format!("invalid request: {error}"))?;
    if head.protocol != protocol {
        return Err(format!("unknown protocol {}", head.protocol));
    }
    serde_json::from_slice(input).map_err(|error| format!("invalid request: {error}"))
}

/// The frame of one request. An error is a request that the core cannot read.
pub(crate) fn answer(input: &[u8]) -> Result<Answered, String> {
    let request: DualRunRequest = decode(input, PROTOCOL)?;
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
    let producer = producer(request.collector_argv.as_ref());
    let (profile, standard_library) = (request.profile, request.standard_library);
    run(Run {
        case: request.case,
        path,
        contract: contract.into_bytes(),
        insides: insides(request.insides)?,
        reply: ReplyInput::bytes(request.reply.map(|bytes| hex(&bytes.hex)).transpose()?),
        sections: request::sections(&request.sections)?,
        namespace: request.namespace,
        roots: request.roots,
        baseline: request.baseline.is_some(),
        report: true,
        base: None,
        trust: Box::new(move |namespace, _| Trust {
            settings: Settings::new(namespace, profile, standard_library).with_producer(producer),
            gap: None,
        }),
        collect: None,
    })
}

/// The reply of a run: none, the bytes of a request, or the reply of the collector that the core
/// ran in its own process (AD-406). Only the scan request makes the last one.
pub(crate) enum ReplyInput {
    Absent,
    Bytes(Vec<u8>),
    Collected(Box<Result<Ingested, String>>),
}

impl ReplyInput {
    pub(crate) fn bytes(reply: Option<Vec<u8>>) -> ReplyInput {
        reply.map_or(ReplyInput::Absent, ReplyInput::Bytes)
    }
}

/// What a request kind gives to the one engine path (`run`): the dual run of the harness
/// (`answer`) or the check request of the shell (`check.rs`). The two kinds differ only here.
pub(crate) struct Run {
    pub(crate) case: String,
    pub(crate) path: String,
    pub(crate) contract: Vec<u8>,
    pub(crate) insides: Vec<InsideFile>,
    pub(crate) reply: ReplyInput,
    pub(crate) sections: Vec<archkeel_model::Section>,
    pub(crate) namespace: String,
    pub(crate) roots: Vec<String>,
    /// A baseline changes what a run reports; no slice reads it yet, so it is refused by name.
    pub(crate) baseline: bool,
    /// True when the frame names the report payload part (the dual run).
    pub(crate) report: bool,
    /// The reading of the base reply of a check request (AD-399); the dual run has none.
    pub(crate) base: Option<BaseOf>,
    /// The settings of the namespace for the validated reply (or none), and a reason that names
    /// the whole contract when the request kind does not trust the reply.
    pub(crate) trust: TrustOf,
    /// The `collect` part of the self-test of a scan request (AD-406); `None` for the others.
    pub(crate) collect: Option<serde_json::Value>,
}

/// How a check request reads its base reply: from the validated candidate reply and the inputs
/// that the base shares, the reason that names the whole contract, or `None` (`base.rs`).
pub(crate) type BaseOf = Box<dyn FnOnce(Option<&Ingested>, Shared) -> Option<String>>;

/// The inputs of the candidate that the base shares: the namespace, the contract and the roots.
pub(crate) struct Shared {
    pub(crate) namespace: String,
    pub(crate) input: ContractInput,
    pub(crate) roots: Vec<String>,
}

/// How a request kind derives its settings from the namespace and the validated reply.
pub(crate) type TrustOf = Box<dyn FnOnce(String, Option<&Ingested>) -> Trust>;

/// The settings that a request kind gives the engine, and a gap of the whole contract.
pub(crate) struct Trust {
    pub(crate) settings: Settings,
    pub(crate) gap: Option<String>,
}

/// The one engine path of each request kind: the reply, the settings, the contract, the rows and
/// the ruling, in this order, and the frame.
pub(crate) fn run(run: Run) -> Result<Answered, String> {
    let mut engine = Engine::default();
    let reply = ingest(&mut engine, run.reply)?;
    let input = ContractInput {
        path: run.path,
        bytes: run.contract,
        insides: run.insides,
    };
    // The base shares the contract of the request: `check` reads both commits under the contract
    // at the baseline commit (AD-399).
    let base = run.base.and_then(|base| {
        let shared = Shared {
            namespace: run.namespace.clone(),
            input: input.clone(),
            roots: run.roots.clone(),
        };
        base(engine.reply(), shared)
    });
    let trust = (run.trust)(run.namespace, engine.reply());
    engine.answer(Request::Settings(settings_of(
        trust.settings,
        &input,
        run.roots,
    )));
    let path = input.path.clone();
    let contract = match engine.answer(Request::Contract(input)) {
        Answer::Contract(state) => state,
        other => ContractState::Refused(format!("unexpected answer {other:?}")),
    };
    let rows = match engine.answer(Request::Sections(run.sections)) {
        Answer::Sections(rows) => rows,
        _ => Vec::new(),
    };
    // The report holds a reason until slice 0d writes the payload, so it is a named gap.
    let report: Result<(), String> = match engine.answer(Request::Report) {
        _ if !run.report => Ok(()),
        Answer::Report(reason) => Err(reason.to_string()),
        other => Err(format!("unexpected answer {other:?}")),
    };
    let mut named = named(&contract, run.baseline, &engine, &path);
    named.contract = named.contract.or(trust.gap).or(base);
    let ruling = match engine.answer(Request::Rules(named)) {
        Answer::Rules(ruling) => ruling,
        other => Err(format!("unexpected answer {other:?}")),
    }
    .map_err(|problem| format!("{}: an inconsistent frame: {problem}", run.case))?;
    let (rows, sections) = crate::sections::split(rows);
    let names_a_gap = report.is_err()
        || !ruling.unsupported().is_empty()
        || !sections.is_empty()
        || !matches!(reply, ReplyCheck::Files(_))
        || !matches!(contract, ContractState::Parsed(_));
    let parts = Parts {
        engine: ENGINE,
        sections: rows,
        unsupported: UnsupportedParts {
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
            collect: run.collect,
        },
        locations: engine
            .reply()
            .into_iter()
            .flat_map(|reply| &reply.reply().facts.evidence)
            .map(|evidence| {
                (
                    evidence.id.as_str().to_owned(),
                    Location {
                        path: evidence.file.clone(),
                        line: evidence.line.max(0),
                    },
                )
            })
            .collect(),
    };
    let frame = ruling
        .frame(&parts)
        .map_err(|error| format!("{}: an inconsistent frame: {error}", run.case))?
        .into_bytes();
    Ok(Answered { frame, names_a_gap })
}

/// The settings of a run: the trusted settings, bound to the root contract and to the scan roots.
/// No roots narrow the run: a receipt that needs them names `Part::ScanRoots`.
pub(crate) fn settings_of(
    settings: Settings,
    input: &ContractInput,
    roots: Vec<String>,
) -> Settings {
    let settings = settings.with_contract_source(&input.path, &input.bytes);
    if roots.is_empty() {
        settings
    } else {
        settings.with_roots(roots)
    }
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

/// The producer of the reply: only the bundled collector, which the shell runs itself. The core
/// cannot verify the pin of an external collector from anything that the caller cannot write, so
/// an external collector is never trusted, pinned or not (AD-388, L-35c). The model also needs
/// the reply to name the collector of its own profile (`Settings::bound`).
fn producer(collector_argv: Option<&Vec<String>>) -> Producer {
    if collector_argv.is_none() {
        Producer::Trusted
    } else {
        Producer::External
    }
}

/// The gaps of the request: a baseline or a contract that the core cannot use names the whole
/// contract, and a UML target names its row. A refused or absent reply gives no model, so the
/// report writes no PASS. The report adds the gaps of the model and writes the status (AD-388).
fn named(contract: &ContractState, baseline: bool, engine: &Engine, path: &str) -> Named {
    let whole = match contract {
        _ if baseline => Some(Reason::Unsupported(Unsupported::Baseline).to_string()),
        ContractState::Parsed(_) => None,
        ContractState::Missing(paths) => Some(crate::contract::missing_reason(paths)),
        ContractState::Refused(message) => Some(format!("refused: {message}")),
    };
    Named {
        rules: crate::contract::uml_reason(engine.usable(), path)
            .into_iter()
            .collect(),
        contract: whole,
        hold: None,
    }
}

/// What the engine knows of the reply of the request, after it ingests the reply.
fn ingest(engine: &mut Engine, reply: ReplyInput) -> Result<ReplyCheck, String> {
    let request = match reply {
        ReplyInput::Absent => {
            let absent = "the request carries no collector reply".to_owned();
            return Ok(ReplyCheck::Absent(absent));
        }
        ReplyInput::Bytes(bytes) => Request::Ingest {
            reply: bytes,
            inflate_limit: INFLATE_LIMIT,
        },
        ReplyInput::Collected(collected) => Request::Collected(request::Collected(collected)),
    };
    Ok(match engine.answer(request) {
        Answer::Reply(ReplyState::Ingested(files)) => ReplyCheck::Files(files),
        Answer::Reply(ReplyState::Refused(message)) => ReplyCheck::Refused(message),
        other => ReplyCheck::Refused(format!("unexpected answer {other:?}")),
    })
}

/// The inside contracts of the request, decoded. The whole request is already read, so the
/// bounds of the count and the size are checked in `contract::answer` and give a named refusal
/// (exit 3), not an unreadable request (AD-379).
pub(crate) fn insides(files: Vec<InsideJson>) -> Result<Vec<InsideFile>, String> {
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
pub(crate) fn hex(text: &str) -> Result<Vec<u8>, String> {
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

#[cfg(test)]
#[path = "hostile_tests.rs"]
mod hostile_tests;
