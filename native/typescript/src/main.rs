// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `archkeel-typescript-collector`: read one collection request on stdin, write one reply.
//!
//! The host spawns this binary like any collector from `[scan].collector_argv`. It bounds time
//! and output, and it validates the reply. A failure exits nonzero with its reason on stderr.
//! The collection is the library of this package (`lib.rs`, AD-406); this file is its thin
//! process wrapper.

#![forbid(unsafe_code)]

use std::io::Read;
#[cfg(feature = "dump")]
use std::io::Write;
use std::process::ExitCode;

use archkeel_typescript_collector::{provenance, reply};
use archkeel_wire::protocol::reply_version;
use archkeel_wire::request::decode;

fn run() -> Result<(), String> {
    let mut payload = Vec::new();
    std::io::stdin()
        .read_to_end(&mut payload)
        .map_err(|error| format!("cannot read the request: {error}"))?;
    let request = decode(&payload)?;
    // The compressed reply goes to stdout as it is made. A failure after the first byte leaves a
    // partial reply and a nonzero exit, which the host refuses.
    let stdout = std::io::stdout();
    reply(
        &request,
        provenance(),
        reply_version(request.protocol_version),
        stdout.lock(),
    )
}

/// Test only: print the syntax facts of the files named on stdin, or with `--dump-records` the
/// records of the request on stdin (`dump.rs`).
#[cfg(feature = "dump")]
fn dump_requested() -> Option<ExitCode> {
    let mode = std::env::args().nth(1)?;
    let stdin = std::io::stdin();
    let mut stdout = std::io::stdout().lock();
    let result = match mode.as_str() {
        "--dump" => archkeel_typescript_collector::dump::run(stdin.lock(), &mut stdout),
        "--dump-count" => archkeel_typescript_collector::dump::count(stdin.lock(), &mut stdout),
        "--dump-umd" => archkeel_typescript_collector::dump::umd(stdin.lock(), &mut stdout),
        "--dump-records" => dump_records(stdin.lock(), &mut stdout),
        _ => return None,
    };
    Some(match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(reason) => {
            eprintln!("archkeel-typescript-collector: {reason}");
            ExitCode::FAILURE
        }
    })
}

#[cfg(feature = "dump")]
fn dump_records(mut input: impl Read, output: &mut impl Write) -> Result<(), String> {
    let mut payload = Vec::new();
    input
        .read_to_end(&mut payload)
        .map_err(|error| format!("cannot read the request: {error}"))?;
    let request = decode(&payload)?;
    let value = archkeel_typescript_collector::dump::records(&request, provenance())?;
    writeln!(output, "{value}").map_err(|error| error.to_string())
}

fn main() -> ExitCode {
    #[cfg(feature = "dump")]
    if let Some(code) = dump_requested() {
        return code;
    }
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(reason) => {
            eprintln!("archkeel-typescript-collector: {reason}");
            ExitCode::FAILURE
        }
    }
}
