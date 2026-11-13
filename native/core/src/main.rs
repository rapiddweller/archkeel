// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-core, slice 0b of WP6 (AD-359, AD-363, epic #880).
//!
//! The one process after the collector. It takes typed requests (`request`): the contract bytes,
//! the collector reply and the sections to write. Today it speaks the engine command of the dual
//! run (`archkeel-core dual-run`, AD-360), the check request of the shell (`archkeel-core check`,
//! AD-390) and the scan request (`archkeel-core scan`, AD-406): for it the core runs the linked
//! collector in its own process through `archkeel-collect` and takes no reply bytes. It decides the rule kinds of slice S1
//! (`complete_assignment`, `root_layout`; AD-370) and S2 (`external_dependency_scope`,
//! `complete_external_scope`; AD-372) and writes their `violations` rows; each part
//! that no slice has ported answers with its name. The shell takes a verdict from a check frame only
//! behind its switch, and only when the frame decides every rule (AD-390).
//!
//! The frame has the status of the run (PASS, FAIL or UNKNOWN) and an explaining row for each
//! rule that is not PASS (AD-361, AD-378). Both come only from the ruling of the report (AD-388). The status is in the frame,
//! not in the exit code. Exit codes: 0 for a frame without a gap, 3 for a frame that names an
//! unsupported or refused part, 2 for a request that the core cannot read or a frame whose
//! status has no explaining row (no frame is written), 1 for an I/O error.

mod base;
mod check;
mod contract;
mod dual_run;
mod engine;
mod ingest;
mod refusal;
mod report;
mod request;
mod rules;
mod scan;
mod sections;
mod topology;

/// The exit code of a frame that names an unsupported or refused part.
const NAMES_A_GAP: u8 = 3;

use std::io::{self, Read, Write};
use std::process::ExitCode;

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    // Three request kinds and one engine path: the dual run of the harness (AD-360), the check
    // request of the shell (AD-390) and the scan request, for which the core runs the collector in
    // its own process (AD-406).
    let answer: Answer = match arguments.as_slice() {
        [kind] if kind == "dual-run" => |input| dual_run::answer(input).map_err(Into::into),
        [kind] if kind == "check" => |input| check::answer(input).map_err(Into::into),
        [kind] if kind == "scan" => scan::answer,
        _ => {
            eprintln!(
                "usage: archkeel-core dual-run|check|scan  (a JSON request on stdin, AD-360, AD-390, \
                 AD-406)"
            );
            return ExitCode::from(2);
        }
    };
    let mut input = Vec::new();
    if let Err(error) = io::stdin().lock().read_to_end(&mut input) {
        eprintln!("archkeel-core: {error}");
        return ExitCode::FAILURE;
    }
    let (code, message) = respond_with(answer, &input, &mut io::stdout().lock());
    if let Some(message) = message {
        eprintln!("{message}");
    }
    ExitCode::from(code)
}

/// The answer of one request kind: the frame and whether it names a gap, or why the core cannot
/// read the request.
type Answer = fn(&[u8]) -> Result<dual_run::Answered, refusal::Error>;

/// Answer one dual-run request (the tests of the frame bytes call this).
#[cfg(test)]
fn respond(input: &[u8], out: &mut impl Write) -> (u8, Option<String>) {
    respond_with(dual_run::answer, input, out)
}

/// Answer one request: the frame is written one time to `out`, or no frame and a message. The
/// first value is the exit code.
fn respond_with<E: From<String>>(
    answer: impl FnOnce(&[u8]) -> Result<dual_run::Answered, E>,
    input: &[u8],
    out: &mut impl Write,
) -> (u8, Option<E>) {
    match answer(input) {
        Ok(answered) => match out.write_all(&answered.frame) {
            Ok(()) if answered.names_a_gap => (NAMES_A_GAP, None),
            Ok(()) => (0, None),
            Err(error) => (1, Some(error.to_string().into())),
        },
        Err(message) => (2, Some(message)),
    }
}

#[cfg(test)]
#[path = "main_tests.rs"]
mod tests;
