// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The native Dart collector (#880, PR 8). Slice 1 holds the discovery: it selects and reads the
//! Dart sources and builds the inputs, the file facts and the gaps of the problems.
//!
//! The collection protocol has no Dart request in `archkeel-facts` yet: `Resolver` has no `dart`
//! variant. Until protocol V10 adds it, the binary refuses a request, and the wheel does not
//! carry it, so the host never runs it and a native Dart reply can never give PASS. The parity
//! tool runs `--dump <snapshot-root> <namespace> <root>...`, which prints the sections as JSON.

mod discover;
mod dump;
mod module;
mod pubspec;
mod pytext;
mod records;

use std::io::Write;
use std::process::ExitCode;

const NO_REQUEST: &str = "archkeel-dart-collector: the collection protocol has no Dart request \
    yet (archkeel-facts Resolver has no dart variant); only --dump is available";

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    let (code, output, message) = match arguments.split_first() {
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
