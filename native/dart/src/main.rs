// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The native Dart collector (#880, PR 8). Slice 1 holds the discovery: it selects and reads the
//! Dart sources and builds the inputs, the file facts and the gaps of the problems.
//!
//! The collection protocol has no Dart request in `archkeel-facts` yet: `Resolver` has no `dart`
//! variant. Until it exists, the binary refuses a request, and the wheel does not carry it, so the
//! host never runs it and a native Dart reply can never give PASS. A build with the test-only
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

use std::io::Write;
use std::process::ExitCode;

const NO_REQUEST: &str = "archkeel-dart-collector: the collection protocol has no Dart request \
    yet (archkeel-facts Resolver has no dart variant)";

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    let (code, output, message) = match arguments.split_first() {
        #[cfg(feature = "dump")]
        Some((flag, rest)) if flag == "--dump" => match dump::run(rest) {
            Ok(text) => (ExitCode::SUCCESS, text, String::new()),
            Err(error) => (ExitCode::from(1), String::new(), error),
        },
        _ => (ExitCode::from(2), String::new(), NO_REQUEST.to_owned()),
    };
    // A closed pipe is the only write failure, and the exit code already tells the result.
    let _ = std::io::stdout().write_all(output.as_bytes());
    if !message.is_empty() {
        let _ = writeln!(std::io::stderr(), "{message}");
    }
    code
}
