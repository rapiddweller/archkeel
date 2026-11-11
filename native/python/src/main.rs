// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `archkeel-python-collector`: read one 10.0.0 request on stdin, write one reply (AD-334).
//!
//! Slice 1b has the parse of one file with the limits of CPython. The import survey of the
//! request follows in slice 1c; until then the binary refuses each request with its reason.

#![forbid(unsafe_code)]

// Slice 1b: only the dump calls the parse; the collection of slice 1c calls it next. The
// expectation fails the build once the parse is used, so it goes with that change.
#[cfg_attr(
    not(any(feature = "dump", test)),
    expect(dead_code, reason = "slice 1c calls the parse")
)]
mod depth;
#[cfg(feature = "dump")]
mod dump;
#[cfg_attr(
    not(any(feature = "dump", test)),
    expect(dead_code, reason = "slice 1c calls the parse")
)]
mod limits;
#[cfg_attr(
    not(any(feature = "dump", test)),
    expect(dead_code, reason = "slice 1c calls the parse")
)]
mod parse;
#[cfg_attr(
    not(any(feature = "dump", test)),
    expect(dead_code, reason = "slice 1c calls the parse")
)]
mod source;

use std::io::Read;
use std::process::ExitCode;

use archkeel_wire::request::decode_python;

/// The stack of the work thread. The parser recurses once for each nested expression, and the
/// token scan bounds that depth before the parse (`limits::MAX_PARSE_DEPTH`).
#[cfg_attr(
    not(feature = "dump"),
    expect(dead_code, reason = "slice 1c runs the scan")
)]
const STACK_BYTES: usize = 256 * 1024 * 1024;

fn run() -> Result<(), String> {
    #[cfg(feature = "dump")]
    {
        let arguments: Vec<String> = std::env::args().collect();
        if let [_, flag, minor, root] = arguments.as_slice() {
            if flag == "--dump" {
                let (minor, root) = (minor.clone(), root.clone());
                return on_big_stack(move || dump::run(&minor, &root));
            }
        }
    }
    let mut payload = Vec::new();
    std::io::stdin()
        .read_to_end(&mut payload)
        .map_err(|error| format!("cannot read the request: {error}"))?;
    let request = decode_python(&payload)?;
    Err(format!(
        "the phase {} of the native Python collector arrives in PR 5 slice 1c",
        request.resolver.phase.as_str()
    ))
}

/// Run `work` on a thread with a stack of `STACK_BYTES`.
#[cfg_attr(
    not(feature = "dump"),
    expect(dead_code, reason = "slice 1c runs the scan")
)]
fn on_big_stack<T: Send + 'static>(
    work: impl FnOnce() -> Result<T, String> + Send + 'static,
) -> Result<T, String> {
    std::thread::Builder::new()
        .stack_size(STACK_BYTES)
        .spawn(work)
        .map_err(|error| format!("cannot start the scan: {error}"))?
        .join()
        .map_err(|_| "the scan stopped without a reply".to_owned())?
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(reason) => {
            eprintln!("archkeel-python-collector: {reason}");
            ExitCode::FAILURE
        }
    }
}
