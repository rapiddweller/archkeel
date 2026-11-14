// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `archkeel-python-collector`: read one 10.0.0 request on stdin, write one reply (AD-334).
//!
//! The binary is a thin caller of the library (AD-450). The reply is the import survey of the
//! Python collector (phase `imports`), never the whole collection.

#![forbid(unsafe_code)]

use std::io::{Read, Write};
use std::process::ExitCode;

use archkeel_python_collector as collector;
use archkeel_wire::request::decode_python;

/// The stack of the work thread. The parser recurses once for each nested expression, and the
/// token scan bounds that depth before the parse (`stack::MAX_STACK`).
const STACK_BYTES: usize = 256 * 1024 * 1024;

#[cfg(feature = "dump")]
fn dump(arguments: &[String]) -> Option<Result<(), String>> {
    use collector::dump;
    if let [_, flag, minor] = arguments {
        if flag == "--dump-printable" {
            return Some(dump::printable(minor));
        }
    }
    let [_, flag, minor, root] = arguments else {
        return None;
    };
    let (minor, root) = (minor.clone(), root.clone());
    Some(match flag.as_str() {
        "--dump" => on_big_stack(move || dump::run(&minor, &root)),
        "--dump-texts" => on_big_stack(move || dump::texts(&minor, &root)),
        "--dump-bindings" => on_big_stack(move || dump::bindings(&minor, &root, false)),
        "--dump-proofs" => on_big_stack(move || dump::bindings(&minor, &root, true)),
        _ => return None,
    })
}

#[cfg(feature = "dump")]
fn dump_request(request: archkeel_facts::request::PythonRequest) -> Option<Result<(), String>> {
    use collector::dump;
    let flag = std::env::args().nth(1)?;
    let found = match flag.as_str() {
        "--dump-scope" => dump::scope(&request),
        "--dump-symbols" => {
            let witnesses = std::env::args().nth(2).as_deref() == Some("1");
            on_big_stack(move || dump::symbols(&request, witnesses))
        }
        "--dump-survey" => on_big_stack(move || dump::survey(&request)),
        _ => return None,
    };
    Some(found.map(|value| println!("{value}")))
}

fn run() -> Result<(), String> {
    #[cfg(feature = "dump")]
    if let Some(done) = dump(&std::env::args().collect::<Vec<_>>()) {
        return done;
    }
    let mut payload = Vec::new();
    std::io::stdin()
        .read_to_end(&mut payload)
        .map_err(|error| format!("cannot read the request: {error}"))?;
    let request = decode_python(&payload)?;
    #[cfg(feature = "dump")]
    if let Some(done) = dump_request(request.clone()) {
        return done;
    }
    let bytes = on_big_stack(move || collector::reply(&request, &collector::BUILD))?;
    std::io::stdout()
        .write_all(&bytes)
        .map_err(|error| format!("cannot write the reply: {error}"))
}

/// Run `work` on a thread with a stack of `STACK_BYTES`.
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
