// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The binary of the native Dart collector (#880): a thin caller of the library.
//!
//! It decodes the Dart request (`archkeel_dart_collector::decode`) and still writes no reply: a
//! valid request gives exit code 2. The wheel does not carry the binary and the host has no
//! launcher for it, so a native Dart reply can never give PASS. A build with the test-only
//! feature `dump` adds `--dump <snapshot-root> <namespace> <root>...`, which prints the sections
//! as JSON for the parity tool, and `--dump-survey <request-file>`, which prints the counts of
//! the import survey (AD-450).

use std::io::{Read, Write};
use std::process::ExitCode;

#[cfg(feature = "dump")]
use archkeel_dart_collector::dump;

const NO_REPLY: &str = "archkeel-dart-collector: the request is valid, but the native Dart \
    collector writes no reply before the wiring of #880";

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    let (code, output, message) = match arguments.split_first() {
        #[cfg(feature = "dump")]
        Some((flag, rest)) if flag == "--dump" => done(dump::run(rest)),
        #[cfg(feature = "dump")]
        Some((flag, rest)) if flag == "--dump-survey" => done(dump::survey(rest)),
        #[cfg(feature = "dump")]
        Some((flag, _))
            if matches!(
                flag.as_str(),
                "--dump-sdk" | "--dump-syntax" | "--dump-declarations" | "--dump-collection"
            ) =>
        {
            let dump = if flag == "--dump-sdk" {
                dump::sdk
            } else if flag == "--dump-declarations" {
                dump::declarations
            } else if flag == "--dump-collection" {
                dump::collection
            } else {
                dump::syntax
            };
            done(read_stdin().and_then(|text| dump(&text)))
        }
        _ => match request() {
            Ok(()) => (ExitCode::from(2), String::new(), NO_REPLY.to_owned()),
            Err(error) => (
                ExitCode::from(1),
                String::new(),
                format!("archkeel-dart-collector: {error}"),
            ),
        },
    };
    // A closed pipe is the only write failure, and the exit code already tells the result.
    let _ = std::io::stdout().write_all(output.as_bytes());
    if !message.is_empty() {
        let _ = writeln!(std::io::stderr(), "{message}");
    }
    code
}

#[cfg(feature = "dump")]
fn done(result: Result<String, String>) -> (ExitCode, String, String) {
    match result {
        Ok(text) => (ExitCode::SUCCESS, text, String::new()),
        Err(error) => (ExitCode::from(1), String::new(), error),
    }
}

/// Read and decode the request on stdin (3.0.0, 8.0.0 or 9.0.0 with the Dart resolver).
fn request() -> Result<(), String> {
    let mut payload = Vec::new();
    std::io::stdin()
        .read_to_end(&mut payload)
        .map_err(|error| format!("cannot read the request: {error}"))?;
    archkeel_dart_collector::decode(&payload).map(|_| ())
}

/// The text on stdin: the file paths of `--dump-syntax`.
#[cfg(feature = "dump")]
fn read_stdin() -> Result<String, String> {
    let mut text = String::new();
    std::io::stdin()
        .read_to_string(&mut text)
        .map_err(|error| format!("cannot read the paths: {error}"))?;
    Ok(text)
}
