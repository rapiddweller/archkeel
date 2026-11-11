// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-core, slice 0b of WP6 (AD-359, AD-363, epic #880).
//!
//! The one process after the collector. It takes typed requests (`request`): the contract bytes,
//! the collector reply and the sections to write. Today it speaks the engine command of the dual
//! run (`archkeel-core dual-run`, AD-360). It owns no section and no rule family yet: each part
//! that no slice has ported answers with its name. The host uses the core for no verdict.
//!
//! Exit codes: 0 for a frame without a gap, 3 for a frame that names an unsupported or refused
//! part, 2 for a request that the core cannot read, 1 for an I/O error.

mod contract;
mod dual_run;
mod engine;
mod ingest;
mod report;
mod request;
mod sections;

/// The exit code of a frame that names an unsupported or refused part.
const NAMES_A_GAP: u8 = 3;

use std::io::{self, Read, Write};
use std::process::ExitCode;

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    if arguments.as_slice() != ["dual-run"] {
        eprintln!("usage: archkeel-core dual-run  (a JSON request on stdin, AD-360)");
        return ExitCode::from(2);
    }
    let mut input = Vec::new();
    if let Err(error) = io::stdin().lock().read_to_end(&mut input) {
        eprintln!("archkeel-core: {error}");
        return ExitCode::FAILURE;
    }
    match dual_run::answer(&input) {
        Ok(answered) => match io::stdout().lock().write_all(&answered.frame) {
            Ok(()) if answered.names_a_gap => ExitCode::from(NAMES_A_GAP),
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                eprintln!("archkeel-core: {error}");
                ExitCode::FAILURE
            }
        },
        Err(message) => {
            eprintln!("archkeel-core: {message}");
            ExitCode::from(2)
        }
    }
}
