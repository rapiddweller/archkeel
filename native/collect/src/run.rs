// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Run the Rust worker or a linked collector and validate the reply (AD-406, AD-881).
//!
//! The request goes through the decode of the wire, the same check that the binary runs on its
//! stdin, so the in-process collector reads exactly the request that the binary would read. The
//! collector runs on a thread with a large stack. A panic of the collector ends that thread: in a
//! test build (unwind) the join gives the panic and this boundary names it as a refusal. In the
//! release build `panic = "abort"` ends the worker for Rust or the core for a linked collector.
//! Both failures give UNKNOWN (exit 2), never a PASS.

use std::time::Duration;

use crate::refusal::{refused, Refusal, RefusalKind};
use archkeel_facts::envelope::{Facts, Profile, Reply};
use archkeel_store::Ingested;
use archkeel_wire::protocol::reply_version;

/// The stack of the collector thread, as the Rust collector binary has it.
const STACK_BYTES: usize = 256 << 20;

/// The typed reply of the request bytes, validated by the store, or why there is none.
#[cfg(test)]
pub(crate) fn collect(profile: Profile, request: &[u8]) -> Result<Ingested, Refusal> {
    collect_timed(profile, request, None).map(|(ingested, _, _)| ingested)
}

/// The typed reply, and the time of the collector and of the validation of its reply (#659).
pub(crate) fn collect_timed(
    profile: Profile,
    request: &[u8],
    clock: Option<&dyn Fn() -> Duration>,
) -> Result<(Ingested, Duration, Duration), Refusal> {
    let started = clock.map(|now| now());
    let reply = if profile == Profile::Rust {
        crate::rust_worker::read(request)?
    } else {
        let request = request.to_vec();
        isolated(move || reply_of(profile, &request))?.map_err(|why| refused("collector", why))?
    };
    let collected = clock
        .zip(started)
        .map_or(Duration::ZERO, |(now, start)| now() - start);
    let validating = clock.map(|now| now());
    let ingested = archkeel_store::ingest_typed(reply).map_err(|reason| {
        refused(
            "collector",
            format!("the store refuses the reply of the collector: {reason}"),
        )
    })?;
    check(&ingested.reply().facts).map_err(|reason| {
        refused(
            "collector",
            format!("the store refuses the reply of the collector: {reason}"),
        )
    })?;
    Ok((
        ingested,
        collected,
        clock
            .zip(validating)
            .map_or(Duration::ZERO, |(now, start)| now() - start),
    ))
}

/// The checks that only the collector of the profile of a reply knows (AD-688). They run after
/// the store has validated the reply with its language-free minimum and the validation block, so
/// they only add rules. The TypeScript and the Rust collector state every rule in their block.
pub fn check(facts: &Facts) -> Result<(), String> {
    match facts.profile {
        Profile::Python => archkeel_python_collector::check(facts),
        Profile::Dart => archkeel_dart_collector::check(facts),
        Profile::TypeScript | Profile::Rust => Ok(()),
    }
}

/// Run `work` on its own thread. A panic is a named error of a test build; see the module text
/// for the release build.
pub(crate) fn isolated<T: Send + 'static>(
    work: impl FnOnce() -> T + Send + 'static,
) -> Result<T, Refusal> {
    let handle = std::thread::Builder::new()
        .name("archkeel-collect".to_owned())
        .stack_size(STACK_BYTES)
        .spawn(move || archkeel_snapshot::work::bounded(work))
        .map_err(|error| {
            refused(
                "collector",
                format!("cannot start the collector thread: {error}"),
            )
        })?;
    handle
        .join()
        .map_err(|panic| {
            let text = panic
                .downcast_ref::<&str>()
                .map(|text| (*text).to_owned())
                .or_else(|| panic.downcast_ref::<String>().cloned())
                .unwrap_or_default();
            refused(
                "collector",
                format!("the collector stopped with a panic: {text}"),
            )
        })?
        .map_err(|limit| Refusal {
            part: "parse work",
            reason: limit.to_string(),
            kind: RefusalKind::ParseWork,
        })
}

/// The typed reply without the store, for the comparison with the bytes of the binary.
pub(crate) fn reply_of(profile: Profile, request: &[u8]) -> Result<Reply, String> {
    archkeel_snapshot::work::bounded(|| match profile {
        Profile::Rust => crate::rust_worker::read(request).map_err(|e| e.to_string()),
        Profile::TypeScript => {
            let request = archkeel_wire::request::decode(request)?;
            archkeel_typescript_collector::typed_reply(
                &request,
                archkeel_typescript_collector::provenance(),
                reply_version(request.protocol_version),
            )
        }
        Profile::Python => {
            let request = archkeel_wire::request::decode_python(request)?;
            archkeel_python_collector::typed_reply(&request, &archkeel_python_collector::BUILD)
        }
        Profile::Dart => {
            let request = archkeel_wire::request::decode_dart(request)?;
            archkeel_dart_collector::typed_reply(
                &request,
                archkeel_dart_collector::provenance(),
                reply_version(request.protocol_version),
            )
        }
    })
    .map_err(|limit| limit.to_string())?
}
