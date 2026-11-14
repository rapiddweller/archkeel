// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One run of a linked collector in the process of the core (AD-406).
//!
//! The request goes through the decode of the wire, the same check that the binary runs on its
//! stdin, so the in-process collector reads exactly the request that the binary would read. The
//! collector runs on a thread with a large stack. A panic of the collector ends that thread: in a
//! test build (unwind) the join gives the panic and this boundary names it as a refusal. In the
//! release build `panic = "abort"` ends the whole core process, as a stack overflow does; the
//! shell then sees a dead core and the run has no verdict (exit 2), never a PASS.

use crate::refusal::{refused, Refusal, RefusalKind};
use archkeel_facts::envelope::{Profile, Reply};
use archkeel_store::Ingested;
use archkeel_wire::protocol::reply_version;

/// The stack of the collector thread, as the Rust collector binary has it.
const STACK_BYTES: usize = 256 << 20;

/// The typed reply of the request bytes, validated by the store, or why there is none.
pub(crate) fn collect(profile: Profile, request: &[u8]) -> Result<Ingested, Refusal> {
    let request = request.to_vec();
    let reply =
        isolated(move || reply_of(profile, &request))?.map_err(|why| refused("collector", why))?;
    archkeel_store::ingest_typed(reply).map_err(|reason| {
        refused(
            "collector",
            format!("the store refuses the reply of the collector: {reason}"),
        )
    })
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
pub fn reply_of(profile: Profile, request: &[u8]) -> Result<Reply, String> {
    archkeel_snapshot::work::bounded(|| match profile {
        Profile::Rust => {
            let request = archkeel_wire::request::decode_rust(request)?;
            archkeel_rust_collector::typed_reply(
                &request,
                archkeel_rust_collector::provenance(),
                reply_version(request.protocol_version),
            )
        }
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
