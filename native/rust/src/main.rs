// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `archkeel-rust-collector`: read one collection request on stdin, write one reply.
//!
//! The host spawns this binary as the collector of `Language.RUST` (AD-335). It bounds time and
//! output, and it validates the reply. A failure exits nonzero with its reason on stderr.

#![forbid(unsafe_code)]

mod attrs;
mod collect;
mod crates;
mod manifest;
mod modules;
mod nesting;
mod net;
mod paths;
mod resolve;
mod scan;
mod source;
mod test_scope;
mod tokens;
mod toml;
mod tree;

use std::io::{Read, Write};
use std::process::ExitCode;

use archkeel_wire::protocol::reply_version;
use archkeel_wire::reply::Provenance;
use archkeel_wire::request::decode_rust;

/// The stack of the scan thread. The system gives address space, not memory, until it is used.
const STACK_BYTES: usize = 256 * 1024 * 1024;

fn provenance() -> Provenance {
    Provenance::native(
        collect::PROFILE,
        (env!("ARCHKEEL_VERSION"), env!("ARCHKEEL_CODE_DIGEST")),
        (
            env!("ARCHKEEL_RUSTC_VERSION"),
            env!("CARGO_PKG_RUST_VERSION"),
        ),
    )
}

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
            collect::collect(&request, provenance()).encode(reply_version(request.version))
        })
        .map_err(|error| format!("cannot start the scan: {error}"))?;
    worker
        .join()
        .map_err(|_| "the scan stopped without a reply".to_owned())?
}

fn main() -> ExitCode {
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
