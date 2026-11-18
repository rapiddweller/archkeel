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
//! the shell gives UNKNOWN without a fallback.

use std::time::Duration;

use serde::Deserialize;
#[cfg(test)]
use serde_json::Value;

use archkeel_collect::{Identity, Over, Refusal, RefusalKind, Scanned};
use archkeel_facts::envelope::validation::library_family;
use archkeel_model::{Producer, Settings};
use archkeel_store::Ingested;

use crate::baseline_frame;
use crate::contract::{ContractInput, ContractState, InsideFile, MAX_INSIDE_FILES};
use crate::dual_run::{self, Answered, Phases, ReplyInput, Run, Trust, TrustOf, CODE_DIGEST};

/// The first words of the reason of a reply that the core cannot verify. The shell counts it.
pub(crate) const PRODUCER_NOT_VERIFIED: &str = "producer not verified";

/// The protocol of the scan request.
const PROTOCOL: &str = "archkeel-core-scan-1";
/// The bounds of the shell on the inside contracts (`cli/native_core.py`): the rounds of a chain
/// of 900 mounts. Each of the root and the inside files has a total byte bound.
const MAX_ROUNDS: usize = 901;
const MAX_BYTES: u64 = 64 << 20;

#[derive(Clone, Deserialize)]
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
    #[serde(default)]
    html: bool,
    #[serde(default)]
    topology: bool,
    /// Give the seconds of the phases on standard error (#659). The frame does not change.
    #[serde(default)]
    timings: bool,
    /// The repository path of the baseline file to compare with (AD-546).
    #[serde(default)]
    baseline: Option<String>,
    /// Write the baseline of this run: the frame carries the bytes (AD-546).
    #[serde(default)]
    write_baseline: bool,
    /// The system document that this configuration is a part of, and the page of the system: the
    /// report page names them and links up (E4, #1451).
    #[serde(default)]
    part_of: Option<PartOfRequest>,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct PartOfRequest {
    /// The repository path of the system document.
    document: String,
    /// The link from the page of the part to the page of the system, as the publisher writes it.
    #[serde(default)]
    href: Option<String>,
}

/// The frame of one scan request. An error is a request that the core cannot read.
pub(crate) fn answer(
    input: &[u8],
    now: &dyn Fn() -> Duration,
) -> Result<Answered, crate::refusal::Error> {
    let request: ScanRequest = crate::decode::decode(input, PROTOCOL)?;
    let clock = request.timings.then_some(now);
    let started = clock.map(|now| now());
    let mut answered = of_request(&request, clock)?;
    answered.timings_asked = request.timings;
    answered.timings = answered.timings.map(|phases| Phases {
        wall: clock
            .zip(started)
            .map_or(Duration::ZERO, |(now, start)| now() - start),
        ..phases
    });
    Ok(answered)
}

fn of_request(
    request: &ScanRequest,
    clock: Option<&dyn Fn() -> Duration>,
) -> Result<Answered, crate::refusal::Error> {
    let identity = Identity {
        root: &request.root,
        config: &request.config,
        discover_root: request.discover_root,
        git_head: request.git_head.as_deref(),
        dirty: request.dirty,
    };
    match archkeel_collect::read_system(&identity) {
        Ok(Some(_)) if request.part_of.is_some() => {
            let reason = "collect: unsupported: --part-of names the system of one part; this configuration is a system document";
            return dual_run::refused_scan(reason, request.html).map_err(Into::into);
        }
        Ok(Some(system)) => return system_run(request, &identity, &system, clock),
        Ok(None) => {}
        Err(refusal) => return refused(&refusal, request.html).map_err(Into::into),
    }
    one(request, &identity, clock)
}

/// The run of a system document (AD-616): one scan for each part, joined into one frame. A part
/// is a scan with the identity of the request and the configuration of the part. The page, the
/// topology and the baseline belong to one part, so a system run refuses them.
fn system_run(
    request: &ScanRequest,
    identity: &Identity<'_>,
    system: &archkeel_collect::System,
    clock: Option<&dyn Fn() -> Duration>,
) -> Result<Answered, crate::refusal::Error> {
    if request.baseline.is_some() || request.write_baseline {
        let reason = "collect: unsupported: a system run has no baseline";
        return dual_run::refused_scan(reason, request.html).map_err(Into::into);
    }
    // Each part gives its topology to the page of the system; the page is one for all parts.
    let part_request = ScanRequest {
        html: false,
        part_of: None,
        topology: request.topology || request.html,
        ..request.clone()
    };
    // A part that the core refused has no timings, so the system has none: never a partial sum.
    let (mut frames, mut names_a_gap, mut timings) = (Vec::new(), false, Some(Phases::default()));
    for part in &system.parts {
        let part_identity = Identity {
            config: &part.config,
            ..*identity
        };
        let answered = one(&part_request, &part_identity, clock)?;
        names_a_gap |= answered.names_a_gap;
        timings = timings
            .zip(answered.timings)
            .map(|(sum, part)| Phases::plus(sum, part));
        frames.push(answered.frame);
    }
    let joining = clock.map(|now| now());
    let frame = crate::system::join(system, &frames, (request.html, request.topology))?;
    Ok(Answered {
        frame,
        names_a_gap,
        timings: timings.map(|sum| Phases {
            join: clock
                .zip(joining)
                .map_or(Duration::ZERO, |(now, start)| now() - start),
            ..sum
        }),
        timings_asked: false,
    })
}

/// The titles of the system of this part, read from the system document of the request (E4).
fn part_of(asked: &PartOfRequest, identity: &Identity<'_>) -> Result<dual_run::PartOf, String> {
    let document = Identity {
        config: &asked.document,
        ..*identity
    };
    let refused = |why: &str| format!("collect: unsupported: --part-of {}: {why}", asked.document);
    let system = match archkeel_collect::read_system(&document) {
        Ok(Some(system)) => system,
        Ok(None) => {
            return Err(refused(
                "not a system document (a .json file of kind system)",
            ))
        }
        Err(refusal) => return Err(refused(&refusal.reason)),
    };
    let part = system
        .parts
        .iter()
        .find(|part| part.config == identity.config)
        .ok_or_else(|| {
            refused(&format!(
                "no part names the configuration {}; name the system document of this part",
                identity.config
            ))
        })?;
    Ok(dual_run::PartOf {
        system: system.title.clone(),
        part: part.title.clone(),
        href: asked.href.clone(),
    })
}

/// The frame of the scan of one configuration.
fn one(
    request: &ScanRequest,
    identity: &Identity<'_>,
    clock: Option<&dyn Fn() -> Duration>,
) -> Result<Answered, crate::refusal::Error> {
    let part_of = match (&request.part_of, request.html) {
        (Some(asked), true) => match part_of(asked, identity) {
            Ok(found) => Some(found),
            Err(reason) => {
                return dual_run::refused_scan(&reason, request.html).map_err(Into::into)
            }
        },
        _ => None,
    };
    match archkeel_collect::scan_with_clock(identity, MAX_BYTES, clock) {
        Ok(scanned) => {
            if request.root_only {
                let input = ContractInput {
                    path: scanned.contract.0.clone(),
                    bytes: scanned.contract.1.clone(),
                    insides: Vec::new(),
                };
                if let ContractState::Missing(paths) = crate::contract::answer(input).0 {
                    return dual_run::refused_scan(
                        &format!(
                            "collect: unsupported: inside contracts: {}",
                            paths.join(", ")
                        ),
                        request.html,
                    )
                    .map_err(Into::into);
                }
            }
            let accept = baseline_input(&scanned, request.baseline.clone(), request.write_baseline);
            let (prepared, collected, validated) =
                (scanned.prepared, scanned.collected, scanned.validated);
            let answered = decide(
                scanned,
                (request.html, request.topology),
                accept,
                part_of,
                clock,
            )?;
            Ok(Answered {
                timings: answered.timings.map(|phases| Phases {
                    prepare: phases.prepare + prepared,
                    collect: collected,
                    validate: validated,
                    ..phases
                }),
                ..answered
            })
        }
        Err(refusal) if refusal.kind == RefusalKind::ParseWork => {
            Err(crate::refusal::Error::Refused(refusal))
        }
        Err(refusal) => refused(&refusal, request.html).map_err(Into::into),
    }
}

/// The run of a scan that `archkeel-collect` completed.
fn decide(
    scanned: Scanned,
    (html, topology): (bool, bool),
    accept: Option<baseline_frame::Input>,
    part_of: Option<dual_run::PartOf>,
    clock: Option<&dyn Fn() -> Duration>,
) -> Result<Answered, String> {
    let reading = clock.map(|now| now());
    let insides = tree(&scanned)?;
    // AD-466: the core reads and binds each provenance document of the tree.
    let documents = crate::provenance::read(&scanned, &insides, MAX_BYTES)?;
    let read = clock
        .zip(reading)
        .map_or(Duration::ZERO, |(now, start)| now() - start);
    let contract_files: std::collections::BTreeMap<_, _> = std::iter::once((
        scanned.contract.0.clone(),
        archkeel_facts::identity::sha256_hex(&scanned.contract.1),
    ))
    .chain(insides.iter().map(|file| {
        (
            file.reference.clone(),
            archkeel_facts::identity::sha256_hex(&file.bytes),
        )
    }))
    .chain(documents.bound())
    .collect();
    let collector = scanned.collector();
    let Scanned {
        roots,
        namespace,
        contract: (path, contract),
        request,
        reply,
        ..
    } = scanned;
    let target = reply.reply().facts.runtime.target_description.clone();
    let facts = &reply.reply().facts;
    let library_key = facts.validation.standard_library.clone();
    let answered = dual_run::run(
        Run {
            case: "scan".to_owned(),
            path,
            contract,
            insides,
            reply: ReplyInput::Collected(Box::new(Ok(reply))),
            sections: Vec::new(),
            namespace,
            roots,
            baseline: false,
            accept,
            report: false,
            html,
            part_of,
            topology,
            base: None,
            trust: in_process(collector),
            collect: Some(crate::dual_run::Collect::Derived {
                request,
                contract_files,
                target,
            }),
            documents: Some(documents),
            sdk_libraries: archkeel_store::sdk_libraries(&library_key)
                .into_iter()
                .map(str::to_owned)
                .collect(),
        },
        clock,
    )?;
    Ok(Answered {
        timings: answered.timings.map(|phases| Phases {
            prepare: read,
            ..phases
        }),
        ..answered
    })
}

/// The baseline of the request: the file read through the safe reader of the inside contracts
/// (a regular file inside the repository, not a link), checked by the contract crate. A file that
/// is absent, too large or damaged is a reason, not a silent "nothing accepted" (AD-546).
fn baseline_input(
    scanned: &Scanned,
    path: Option<String>,
    write: bool,
) -> Option<baseline_frame::Input> {
    let read = path.map(|path| {
        let limit = u64::try_from(archkeel_contract::policy::MAX_BASELINE_BYTES).unwrap_or(0);
        let file = match scanned.read_inside(&path, limit) {
            Ok(Some((_, bytes))) => archkeel_contract::policy::parse_baseline(&bytes)
                .map_err(|error| format!("{path}: {error}")),
            Ok(None) => Err(format!(
                "{path}: not a regular file inside the repository, or not readable"
            )),
            Err(Over(_)) => Err(format!("{path}: more than {limit} bytes")),
        };
        (path, file)
    });
    match (read, write) {
        (None, false) => None,
        (None, true) => Some(baseline_frame::Input::Write),
        (Some((path, file)), false) => Some(baseline_frame::Input::Compare { path, file }),
        (Some((path, file)), true) => Some(baseline_frame::Input::CompareAndWrite { path, file }),
    }
}

/// The frame of a scan that `archkeel-collect` refused: no reply and no contract, and the
/// `collect` part names why. The frame decides nothing, so the shell gives UNKNOWN.
fn refused(refusal: &Refusal, html: bool) -> Result<Answered, String> {
    dual_run::refused_scan(&refusal.to_string(), html)
}

/// The trust of the scan request: the reply comes from the collector that this process ran.
/// The reply must still name the collector of the profile that ran and the code digest of this
/// build; anything else names the whole contract.
fn in_process(collector: &'static str) -> TrustOf {
    Box::new(move |namespace, reply: Option<&Ingested>| {
        let Some(reply) = reply else {
            return Trust {
                settings: Settings::new(namespace, String::new(), Vec::new()),
                gap: None,
            };
        };
        let facts = &reply.reply().facts;
        let key = facts.validation.standard_library.clone();
        let Some(standard_library) = archkeel_store::standard_library_at(&key) else {
            let names = archkeel_store::standard_library_everywhere(&key)
                .into_iter()
                .map(str::to_owned)
                .collect();
            return Trust {
                settings: Settings::new(namespace, collector.to_owned(), names),
                gap: Some("the target has no standard library table".to_owned()),
            };
        };
        let standard_library = standard_library.into_iter().map(str::to_owned).collect();
        let settings = Settings::new(namespace, collector.to_owned(), standard_library);
        let adapter = &facts.adapter;
        if facts.profile.as_str() == collector
            && adapter.name == collector
            && library_family(&key) == adapter.name
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
                collector, adapter.name, adapter.code_digest
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
pub(crate) mod tests;

#[cfg(test)]
#[path = "scan_work_tests.rs"]
mod work_tests;
