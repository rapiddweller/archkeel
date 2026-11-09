// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `archkeel-typescript-collector`: read one collection request on stdin, write one reply.
//!
//! The host spawns this binary like any collector from `[scan].collector_argv`. It bounds time
//! and output, and it validates the reply. A failure exits nonzero with its reason on stderr.

#![forbid(unsafe_code)]

mod ancestors;
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
mod jsdoc;
mod kinds;
mod layer;
mod manifest;
mod members;
mod options;
mod parse;
mod paths;
mod pytext;
mod references;
mod resolve;
mod scan;
mod scope;
mod site_names;
mod site_paths;
mod site_syntax;
mod site_types;
mod sites;
mod snapshot;
mod source;
mod source_input;
mod syntax;
mod test_sources;
#[cfg(test)]
mod test_tree;
mod walk;

use std::io::{Read, Write};
use std::process::ExitCode;

use archkeel_wire::protocol::reply_version;
use archkeel_wire::reply::{encode, Provenance};
use archkeel_wire::request::decode;

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
    let request = decode(&payload)?;
    let facts = collect::collect(&request, provenance());
    encode(reply_version(request.version), &facts)
}

/// Test only: print the syntax facts of the files named on stdin (`dump.rs`).
#[cfg(feature = "dump")]
fn dump_requested() -> Option<ExitCode> {
    if std::env::args().nth(1).as_deref() != Some("--dump") {
        return None;
    }
    let stdin = std::io::stdin();
    let mut stdout = std::io::stdout().lock();
    Some(match dump::run(stdin.lock(), &mut stdout) {
        Ok(()) => ExitCode::SUCCESS,
        Err(reason) => {
            eprintln!("archkeel-typescript-collector: {reason}");
            ExitCode::FAILURE
        }
    })
}

fn main() -> ExitCode {
    #[cfg(feature = "dump")]
    if let Some(code) = dump_requested() {
        return code;
    }
    match run() {
        Ok(reply) => match std::io::stdout().write_all(&reply) {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                eprintln!("archkeel-typescript-collector: cannot write the reply: {error}");
                ExitCode::FAILURE
            }
        },
        Err(reason) => {
            eprintln!("archkeel-typescript-collector: {reason}");
            ExitCode::FAILURE
        }
    }
}
