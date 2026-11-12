// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `archkeel-python-collector`: read one 10.0.0 request on stdin, write one reply (AD-334).
//!
//! The reply is the import survey of the Python collector (phase `imports`), never the whole
//! collection: it declares only the sections of the survey (`reply.rs`, AD-334).

#![forbid(unsafe_code)]

mod depth;
mod discover;
#[cfg(feature = "dump")]
mod dump;
mod identifier;
mod inputs;
mod limits;
mod names;
mod parse;
mod reply;
mod requirement;
mod source;
mod stack;
mod survey;

use std::io::{Read, Write};
use std::process::ExitCode;

use archkeel_wire::request::decode_python;

/// The stack of the work thread. The parser recurses once for each nested expression, and the
/// token scan bounds that depth before the parse (`stack::MAX_STACK`).
const STACK_BYTES: usize = 256 * 1024 * 1024;

/// The version and the code digest of this binary (`archkeel-build-support`).
const BUILD: reply::Build<'static> = reply::Build {
    version: env!("ARCHKEEL_VERSION"),
    code_digest: env!("ARCHKEEL_CODE_DIGEST"),
};

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
    #[cfg(feature = "dump")]
    if std::env::args().nth(1).as_deref() == Some("--dump-scope") {
        println!("{}", dump::scope(&request)?);
        return Ok(());
    }
    #[cfg(feature = "dump")]
    if std::env::args().nth(1).as_deref() == Some("--dump-survey") {
        let found = on_big_stack(move || dump::survey(&request))?;
        println!("{found}");
        return Ok(());
    }
    let bytes = on_big_stack(move || {
        let found = survey::survey(&request)?;
        reply::reply(&request, found, &BUILD)
    })?;
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
