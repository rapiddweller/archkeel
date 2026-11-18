// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `archkeel-rust-collector`: read one collection request on stdin, write one reply.
//!
//! The host spawns this binary as the collector of `Language.RUST` (AD-335). It bounds time and
//! output, and it validates the reply. A failure exits nonzero with its reason on stderr.

#![forbid(unsafe_code)]

use std::io::{BufRead, Read, Write};
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

fn private() -> Result<(), String> {
    let mut payload = String::new();
    std::io::stdin()
        .lock()
        .take(1 << 20)
        .read_line(&mut payload)
        .map_err(|e| e.to_string())?;
    if !payload.ends_with('\n') {
        return Err("incomplete worker request".into());
    }
    let request = decode_rust(payload.as_bytes())?;
    // EOF means the parent has died or cancelled the scan.
    std::thread::spawn(|| {
        let mut byte = [0];
        let _ = std::io::stdin().read(&mut byte);
        std::process::exit(2);
    });
    let answer = std::thread::Builder::new()
        .stack_size(STACK_BYTES)
        .spawn(move || {
            if !TEST_FEATURES.is_empty() {
                return Ok(Err("test-feature worker".into()));
            }
            archkeel_snapshot::work::bounded(|| {
                typed_reply(
                    &request,
                    provenance(),
                    reply_version(request.protocol_version),
                )
            })
            .map_err(|limit| limit.to_string())
        })
        .map_err(|e| e.to_string())?
        .join()
        .map_err(|_| "worker panic")?;
    archkeel_wire::worker::write_rust_v1(std::io::stdout().lock(), answer)
}

fn main() -> ExitCode {
    if std::env::args_os().nth(1).as_deref()
        == Some(std::ffi::OsStr::new(archkeel_wire::worker::RUST_WORKER_V1))
    {
        return match private() {
            Ok(()) => ExitCode::SUCCESS,
            Err(why) => {
                // Nothing is written before a failure of the frame itself, so this is the one frame.
                let _ =
                    archkeel_wire::worker::write_rust_v1(std::io::stdout().lock(), Ok(Err(why)));
                ExitCode::FAILURE
            }
        };
    }
    match run().and_then(|reply| {
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
