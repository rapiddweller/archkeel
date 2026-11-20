// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `archkeel-rust-collector`: read one collection request on stdin, write one reply.
//!
//! The host spawns this binary as the collector of `Language.RUST` (AD-335). It bounds time and
//! output, and it validates the reply. A failure exits nonzero with its reason on stderr.

#![forbid(unsafe_code)]

mod scip_evidence;

use std::io::{Read, Write};
use std::process::ExitCode;

use archkeel_rust_collector::{encoded_reply, provenance, typed_reply, TEST_FEATURES};
use archkeel_wire::protocol::reply_version;
use archkeel_wire::request::decode_rust;

/// The stack of the scan thread. The system gives address space, not memory, until it is used.
const STACK_BYTES: usize = 256 * 1024 * 1024;

fn run() -> Result<Vec<u8>, String> {
    let mut payload = Vec::new();
    std::io::stdin()
        .read_to_end(&mut payload)
        .map_err(|error| format!("cannot read the request: {error}"))?;
    let request = decode_rust(&payload)?;
    // The walk over a tree of `syn` uses one frame for each level. A big stack and the limit of
    // `nesting.rs` together mean that no file ends the whole scan.
    let worker = std::thread::Builder::new()
        .stack_size(STACK_BYTES)
        .spawn(move || {
            encoded_reply(
                &request,
                provenance(),
                reply_version(request.protocol_version),
            )
        })
        .map_err(|error| format!("cannot start the scan: {error}"))?;
    worker
        .join()
        .map_err(|_| "the scan stopped without a reply".to_owned())?
}

fn main() -> ExitCode {
    if std::env::args_os().nth(1).as_deref() == Some(std::ffi::OsStr::new("scip-evidence")) {
        return finish(scip_evidence::run(STACK_BYTES).map(|()| Vec::new()));
    }
    if let Some(exit) =
        archkeel_wire::worker::serve_v1(decode_rust, TEST_FEATURES, |request, version| {
            archkeel_snapshot::work::bounded(|| typed_reply(request, provenance(), version))
        })
    {
        return exit;
    }
    finish(run())
}

fn finish(result: Result<Vec<u8>, String>) -> ExitCode {
    match result.and_then(|reply| {
        std::io::stdout()
            .write_all(&reply)
            .map_err(|error| format!("cannot write the reply: {error}"))
    }) {
        Ok(()) => ExitCode::SUCCESS,
        Err(reason) => {
            eprintln!("archkeel-rust-collector: {reason}");
            ExitCode::FAILURE
        }
    }
}
