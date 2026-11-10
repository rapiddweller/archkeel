// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The store process: `archkeel-store --inflate-limit <bytes>` answers the frames on stdin.

use std::io::{self, BufReader, BufWriter};
use std::process::ExitCode;

fn limit() -> Result<u64, String> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    match arguments.as_slice() {
        [flag, value] if flag == "--inflate-limit" => value
            .parse()
            .map_err(|_| format!("invalid inflate limit {value}")),
        _ => Err("usage: archkeel-store --inflate-limit <bytes>".to_owned()),
    }
}

fn main() -> ExitCode {
    let limit = match limit() {
        Ok(limit) => limit,
        Err(message) => {
            eprintln!("{message}");
            return ExitCode::from(2);
        }
    };
    let mut input = BufReader::new(io::stdin().lock());
    let mut output = BufWriter::new(io::stdout().lock());
    match archkeel_store::session::run(&mut input, &mut output, limit) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("archkeel-store: {error}");
            ExitCode::FAILURE
        }
    }
}
