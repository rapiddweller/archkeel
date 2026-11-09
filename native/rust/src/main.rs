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
mod paths;
mod resolve;
mod scan;
mod source;
#[cfg(test)]
mod test_tree;
mod tokens;
mod toml;
mod tree;

use std::io::{Read, Write};
use std::process::ExitCode;

use archkeel_wire::protocol::reply_version;
use archkeel_wire::reply::{encode, Provenance};
use archkeel_wire::request::decode_rust;

fn provenance() -> Provenance {
    Provenance {
        profile: collect::PROFILE,
        adapter_version: env!("ARCHKEEL_VERSION").to_owned(),
        code_digest: env!("ARCHKEEL_CODE_DIGEST").to_owned(),
        runtime_name: "rust",
        runtime_version: env!("ARCHKEEL_RUSTC_VERSION").to_owned(),
        runtime_required: format!(">={}", env!("CARGO_PKG_RUST_VERSION")),
    }
}

fn run() -> Result<Vec<u8>, String> {
    let mut payload = Vec::new();
    std::io::stdin()
        .read_to_end(&mut payload)
        .map_err(|error| format!("cannot read the request: {error}"))?;
    let request = decode_rust(&payload)?;
    let facts = collect::collect(&request, provenance());
    encode(reply_version(request.version), &facts)
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
