// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! archkeel-core, slice 0b of WP6 (AD-359, AD-363, epic #880).
//!
//! The one process after the collector. A release binary speaks one request kind, the scan request
//! (`archkeel-core scan`, AD-406): the core runs the linked collector in its own process through
//! `archkeel-collect` and takes no reply bytes. The kinds `dual-run` (AD-360) and `check` (AD-390)
//! carry a collector reply and trust it, so they exist in test builds and with the feature
//! `harness` only (#1095). The core decides the rule kinds of the contract and writes their
//! `violations` rows; each part that no slice has ported answers with its name.
//!
//! The frame has the status of the run (PASS, FAIL or UNKNOWN) and an explaining row for each
//! rule that is not PASS (AD-361, AD-378). Both come only from the ruling of the report (AD-388). The status is in the frame,
//! not in the exit code. Exit codes: 0 for a frame without a gap, 3 for a frame that names an
//! unsupported or refused part, 2 for a request that the core cannot read or a frame whose
//! status has no explaining row (no frame is written), 1 for an I/O error.

mod baseline;
mod baseline_frame;
mod contract;
mod decode;
mod dual_run;
mod engine;
mod gap_key;
mod hygiene;
mod hygiene_boundary;
mod hygiene_graph;
mod hygiene_interface;
mod hygiene_pairs;
mod hygiene_refs;
mod ingest;
mod provenance;
mod refusal;
mod report;
mod request;
mod rules;
mod scan;
mod section_rows;
mod sections;
mod system;
mod system_topology;
mod topology;
mod topology_declared;
mod topology_projection;

/// The exit code of a frame that names an unsupported or refused part.
const NAMES_A_GAP: u8 = 3;
/// The bytes of a scan request: the root, the config and a few flags. The core reads the files.
const SCAN_REQUEST_LIMIT: u64 = 1 << 20;
/// The bytes of a request that carries a collector reply as hex text (the harness and the check
/// request): twice the largest reply that the store accepts.
#[cfg(any(test, feature = "harness"))]
const REPLY_REQUEST_LIMIT: u64 = 1 << 30;

use std::io::{self, Read, Write};
use std::process::ExitCode;

// The request kinds that carry a reply (#1095): test builds and the feature `harness` only.
#[cfg(any(test, feature = "harness"))]
mod base;
#[cfg(any(test, feature = "harness"))]
mod check;

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    // One request kind in a production build: the scan request, for which the core runs the
    // collector in its own process (AD-406). The `dual-run` and `check` kinds carry a collector
    // reply and trust it, so they exist in test builds and with the feature `harness` only
    // (#1095): no caller of a release binary can make a producer trusted.
    let (answer, limit): (Answer, u64) = match arguments.as_slice() {
        #[cfg(any(test, feature = "harness"))]
        [kind] if kind == "dual-run" => (
            |input| dual_run::answer(input).map_err(Into::into),
            REPLY_REQUEST_LIMIT,
        ),
        #[cfg(any(test, feature = "harness"))]
        [kind] if kind == "check" => (
            |input| check::answer(input).map_err(Into::into),
            REPLY_REQUEST_LIMIT,
        ),
        [kind] if kind == "scan" => (scan::answer, SCAN_REQUEST_LIMIT),
        _ => {
            eprintln!("usage: archkeel-core scan  (a JSON request on stdin, AD-406)");
            return ExitCode::from(2);
        }
    };
    let input = match read_request(io::stdin().lock(), limit) {
        Ok(input) => input,
        Err(Unread::Over) => {
            eprintln!("archkeel-core: the request is larger than {limit} bytes");
            return ExitCode::from(2);
        }
        Err(Unread::Io(error)) => {
            eprintln!("archkeel-core: {error}");
            return ExitCode::FAILURE;
        }
    };
    let (code, message) = respond_with(answer, &input, &mut io::stdout().lock());
    if let Some(message) = message {
        eprintln!("{message}");
    }
    ExitCode::from(code)
}

/// Why a request was not read.
#[derive(Debug)]
enum Unread {
    /// More than the limit: the rest of stdin is never read.
    Over,
    Io(io::Error),
}

/// Read the request, at most `limit` bytes. The read stops one byte after the limit, so the memory
/// of a refused request is bounded by the limit and not by the size of stdin.
fn read_request(input: impl Read, limit: u64) -> Result<Vec<u8>, Unread> {
    let mut bytes = Vec::new();
    input
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(Unread::Io)?;
    if bytes.len() as u64 > limit {
        return Err(Unread::Over);
    }
    Ok(bytes)
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
mod frame_schema;
#[cfg(test)]
#[path = "main_tests.rs"]
mod tests;

// Probe a 3 of the PR gate time.
