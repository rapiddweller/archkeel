// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `archkeel-typescript-collector`: read one collection request on stdin, write one reply.
//!
//! The host spawns this binary like any collector from `[scan].collector_argv`. It bounds time
//! and output, and it validates the reply. A failure exits nonzero with its reason on stderr.

#![forbid(unsafe_code)]

mod ancestors;
mod cited;
mod class_members;
mod collect;
mod concerns;
mod config;
mod constructors;
mod definitions;
mod discover;
#[cfg(feature = "dump")]
mod dump;
mod exports;
mod glob;
mod import_bindings;
mod installed;
mod jsdoc;
mod kept;
mod kinds;
mod layer;
mod layout;
mod manifest;
mod members;
mod options;
mod parse;
mod pytext;
mod records;
mod references;
mod resolution;
mod resolve;
mod scan;
mod scope;
mod script;
mod script_alias;
mod script_bind;
mod script_declarations;
mod script_declare;
mod script_factory;
mod script_flags;
mod script_index;
mod script_names;
mod script_namespace;
mod script_publish;
mod script_refs;
mod script_scope;
mod script_syntax;
mod script_types;
mod script_wrapper;
mod script_writes;
mod site_names;
mod site_paths;
mod site_records;
mod site_syntax;
mod site_types;
mod sites;
mod source;
mod source_input;
mod symbol_table;
mod symbols;
mod syntax;
mod test_sources;
mod umd;
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
mod umd_publication;
mod walk;

use std::io::Read;
#[cfg(feature = "dump")]
use std::io::Write;
use std::process::ExitCode;

use archkeel_facts::envelope::Profile;
use archkeel_facts::envelope::Provenance;
use archkeel_wire::protocol::reply_version;
use archkeel_wire::request::decode;

fn provenance() -> Provenance {
    Provenance::native(
        Profile::TypeScript,
        (env!("ARCHKEEL_VERSION"), env!("ARCHKEEL_CODE_DIGEST")),
        (
            env!("ARCHKEEL_RUSTC_VERSION"),
            env!("CARGO_PKG_RUST_VERSION"),
        ),
    )
}

fn run() -> Result<(), String> {
    let mut payload = Vec::new();
    std::io::stdin()
        .read_to_end(&mut payload)
        .map_err(|error| format!("cannot read the request: {error}"))?;
    let request = decode(&payload)?;
    // The compressed reply goes to stdout as it is made. A failure after the first byte leaves a
    // partial reply and a nonzero exit, which the host refuses.
    let stdout = std::io::stdout();
    collect::reply(
        &request,
        provenance(),
        reply_version(request.version),
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
        "--dump" => dump::run(stdin.lock(), &mut stdout),
        "--dump-count" => dump::count(stdin.lock(), &mut stdout),
        "--dump-umd" => dump::umd(stdin.lock(), &mut stdout),
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
    let value = dump::records(&request, provenance())?;
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
