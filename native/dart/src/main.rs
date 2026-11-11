// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The native Dart collector (#880, PR 8). Slice 1 holds the discovery: it selects and reads the
//! Dart sources and builds the inputs, the file facts and the gaps of the problems.
//!
//! Slice 2 decodes the Dart request (`archkeel_wire::request::decode_dart`) and still writes no
//! reply: a valid request gives exit code 2. The wheel does not carry the binary and the host has
//! no launcher for it, so a native Dart reply can never give PASS before slice 5. A build with the test-only
//! feature `dump` adds `--dump <snapshot-root> <namespace> <root>...`, which prints the sections
//! as JSON for the parity tool.

// The request path of slice 2 uses these modules. Until then only the dump uses them, so a build
// without the `dump` feature holds unused code; the expectation fails once the code is used.
#![cfg_attr(
    not(feature = "dump"),
    expect(
        dead_code,
        reason = "slice 2 of #880 adds the request path that uses the discovery"
    )
)]

mod discover;
#[cfg(feature = "dump")]
mod dump;
mod module;
mod pubspec;
mod pytext;
mod records;

use std::io::{Read, Write};
use std::process::ExitCode;

const NO_REPLY: &str = "archkeel-dart-collector: the request is valid, but the native Dart \
    collector writes no reply before slice 5 of #880";

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    let (code, output, message) = match arguments.split_first() {
        #[cfg(feature = "dump")]
        Some((flag, rest)) if flag == "--dump" => match dump::run(rest) {
            Ok(text) => (ExitCode::SUCCESS, text, String::new()),
            Err(error) => (ExitCode::from(1), String::new(), error),
        },
        _ => match request() {
            Ok(()) => (ExitCode::from(2), String::new(), NO_REPLY.to_owned()),
            Err(error) => (ExitCode::from(1), String::new(), error),
        },
    };
    // A closed pipe is the only write failure, and the exit code already tells the result.
    let _ = std::io::stdout().write_all(output.as_bytes());
    if !message.is_empty() {
        let _ = writeln!(std::io::stderr(), "{message}");
    }
    code
}

/// Read and decode the request on stdin (3.0.0, 8.0.0 or 9.0.0 with the Dart resolver).
fn request() -> Result<(), String> {
    let mut payload = Vec::new();
    std::io::stdin()
        .read_to_end(&mut payload)
        .map_err(|error| format!("cannot read the request: {error}"))?;
    archkeel_wire::request::decode_dart(&payload).map(|_| ())
}
