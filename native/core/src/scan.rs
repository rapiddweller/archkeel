// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scan request of the shell (AD-406): the core runs the collector in its own process.
//!
//! The request carries only the scan identity: the repository root, the location of the
//! configuration, and the Git head and dirty state that the shell read. It has no reply, digest,
//! profile, root list or trust field: `deny_unknown_fields` refuses a request that names one
//! (exit 2), so no caller can give this kind facts. `archkeel-collect` reads the configuration
//! and the contract, derives the request, runs the linked collector and gives the store its typed
//! reply. The core then reads the inside contracts through the same reader, in the rounds of the
//! shell (AD-379), and sends the run through the one engine path (`dual_run::run`).
//!
//! Trust: `Producer::Trusted` comes from the fact that the core ran the linked collector itself
//! (`in_process`). It is not `check::stage_one_shell_trust`, which stays the only trust path of the
//! check request. A part that `archkeel-collect` cannot run (another profile, a configured
//! collector, a hostile repository over the work budget) is a frame that names it (exit 3), and
//! the shell keeps its stage 1 path.

use serde::Deserialize;
use serde_json::json;
#[cfg(test)]
use serde_json::Value;

use archkeel_collect::{Identity, Over, Profile, Refusal, Scanned};
use archkeel_model::{Producer, Settings};
use archkeel_store::Ingested;

use crate::check::{CODE_DIGEST, PRODUCER_NOT_VERIFIED};
use crate::contract::{ContractInput, ContractState, InsideFile, MAX_INSIDE_FILES};
use crate::dual_run::{self, Answered, ReplyInput, Run, Trust, TrustOf};

/// The protocol of the scan request.
const PROTOCOL: &str = "archkeel-core-scan-1";
/// The bounds of the shell on the inside contracts (`cli/native_core.py`): the rounds of a chain
/// of 900 mounts and the bytes of the contract and of all inside contracts.
const MAX_ROUNDS: usize = 901;
const MAX_BYTES: u64 = 64 << 20;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ScanRequest {
    // Checked before through `dual_run::decode`.
    #[serde(rename = "protocol")]
    _protocol: String,
    root: String,
    config: String,
    #[serde(default)]
    git_head: Option<String>,
    #[serde(default)]
    dirty: Option<bool>,
    #[serde(default)]
    root_only: bool,
    #[serde(default)]
    discover_root: bool,
}

/// The frame of one scan request. An error is a request that the core cannot read.
pub(crate) fn answer(input: &[u8]) -> Result<Answered, String> {
    let request: ScanRequest = dual_run::decode(input, PROTOCOL)?;
    let identity = Identity {
        root: &request.root,
        config: &request.config,
        discover_root: request.discover_root,
        git_head: request.git_head.as_deref(),
        dirty: request.dirty,
    };
    match archkeel_collect::scan(&identity, MAX_BYTES) {
        Ok(scanned) => {
            if request.root_only {
                let input = ContractInput {
                    path: scanned.contract.0.clone(),
                    bytes: scanned.contract.1.clone(),
                    insides: Vec::new(),
                };
                if let ContractState::Missing(paths) = crate::contract::answer(input).0 {
                    return dual_run::refused_scan(&format!(
                        "collect: unsupported: inside contracts: {}",
                        paths.join(", ")
                    ));
                }
            }
            decide(scanned)
        }
        Err(refusal) => refused(&refusal),
    }
}

/// The run of a scan that `archkeel-collect` completed.
fn decide(scanned: Scanned) -> Result<Answered, String> {
    let insides = tree(&scanned)?;
    let Scanned {
        profile,
        roots,
        namespace,
        contract: (path, contract),
        request,
        reply,
        ..
    } = scanned;
    dual_run::run(Run {
        case: "scan".to_owned(),
        path,
        contract,
        insides,
        reply: ReplyInput::Collected(Box::new(Ok(reply))),
        sections: Vec::new(),
        namespace,
        roots,
        baseline: false,
        report: false,
        base: None,
        trust: in_process(profile),
        collect: Some(json!({ "request": request })),
    })
}

/// The frame of a scan that `archkeel-collect` refused: no reply and no contract, and the
/// `collect` part names why. The frame decides nothing, so the shell keeps its stage 1 path.
fn refused(refusal: &Refusal) -> Result<Answered, String> {
    dual_run::refused_scan(&refusal.to_string())
}

/// The trust of the scan request: the reply comes from the collector that this process ran.
/// The reply must still name the collector of the profile that ran and the code digest of this
/// build; anything else names the whole contract.
fn in_process(profile: Profile) -> TrustOf {
    Box::new(move |namespace, reply: Option<&Ingested>| {
        let Some(reply) = reply else {
            return Trust {
                settings: Settings::new(namespace, String::new(), Vec::new()),
                gap: None,
            };
        };
        let standard_library = archkeel_store::standard_library(profile)
            .into_iter()
            .map(str::to_owned)
            .collect();
        let settings = Settings::new(namespace, profile.as_str().to_owned(), standard_library);
        let facts = &reply.reply().facts;
        let adapter = &facts.adapter;
        if facts.profile == profile
            && adapter.name == profile.as_str()
            && adapter.code_digest == CODE_DIGEST
        {
            return Trust {
                settings: settings.with_producer(Producer::Trusted),
                gap: None,
            };
        }
        Trust {
            settings,
            gap: Some(format!(
                "{PRODUCER_NOT_VERIFIED}: the collector in the core process ran for {} and its \
                 reply names the adapter {} with the code digest {}",
                profile.as_str(),
                adapter.name,
                adapter.code_digest
            )),
        }
    })
}

/// The inside contracts of the root contract, read in the rounds of the shell (AD-379): each
/// round names the paths that the tree still needs, and a round that reads no new file ends the
/// loop, so the frame names each path that the core cannot read. The bounds of the shell give an
/// error (exit 2), as they give a `CoreError` in the shell.
fn tree(scanned: &Scanned) -> Result<Vec<InsideFile>, String> {
    let (path, bytes) = &scanned.contract;
    let mut sent: Vec<InsideFile> = Vec::new();
    let mut total: u64 = 0;
    for _ in 0..MAX_ROUNDS {
        let input = ContractInput {
            path: path.clone(),
            bytes: bytes.clone(),
            insides: sent.clone(),
        };
        let ContractState::Missing(paths) = crate::contract::answer(input).0 else {
            return Ok(sent);
        };
        let mut added = false;
        for reference in paths {
            if sent.iter().any(|file| file.reference == reference) {
                continue;
            }
            if sent.len() >= MAX_INSIDE_FILES {
                return Err(format!(
                    "the tree needs more than {MAX_INSIDE_FILES} inside contracts"
                ));
            }
            match scanned.read_inside(&reference, MAX_BYTES.saturating_sub(total)) {
                Ok(Some((identity, bytes))) => {
                    total = total.saturating_add(bytes.len() as u64);
                    sent.push(InsideFile {
                        reference,
                        identity,
                        bytes,
                    });
                    added = true;
                }
                Ok(None) => {}
                Err(Over(_)) => {
                    return Err(format!(
                        "the inside contracts hold more than {MAX_BYTES} bytes"
                    ))
                }
            }
        }
        if !added {
            return Ok(sent);
        }
    }
    Err(format!("the tree needs more than {MAX_ROUNDS} rounds"))
}

/// The derived request of a frame, for the tests.
#[cfg(test)]
pub(crate) fn derived(frame: &Value) -> Option<&Value> {
    frame.get("self_test")?.get("collect")?.get("request")
}

#[cfg(test)]
#[path = "scan_tests.rs"]
mod tests;
