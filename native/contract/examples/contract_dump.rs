// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The parity probe of `tests/test_rust_contract_parity.py`: it reads contracts from standard
//! input and writes one JSON line for each, with the decision, the error kind and the canonical
//! bytes. A contract is framed as its length in decimal, a line feed, then its bytes.

use std::io::{self, BufRead, Read, Write};

use archkeel_contract::{canonical_bytes, canonical_digest, parse, ErrorKind};
use serde_json::{json, Value};

fn kind(error: ErrorKind) -> &'static str {
    match error {
        ErrorKind::Invalid => "invalid",
        ErrorKind::Version => "version",
        ErrorKind::Input => "input",
        ErrorKind::DuplicateKey => "duplicate_key",
    }
}

fn line(bytes: &[u8]) -> Value {
    match parse(bytes) {
        Ok(contract) => json!({
            "kind": "accept",
            "canonical": String::from_utf8_lossy(&canonical_bytes(&contract)),
            "digest": contract.digest().as_text(),
            "canonical_digest": canonical_digest(&contract).as_text(),
        }),
        Err(error) => {
            json!({"kind": kind(error.kind), "message": error.message})
        }
    }
}

fn main() -> io::Result<()> {
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    let mut header = String::new();
    loop {
        header.clear();
        if input.read_line(&mut header)? == 0 {
            return Ok(());
        }
        let size: usize = header
            .trim()
            .parse()
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "a frame needs its length"))?;
        let mut bytes = vec![0; size];
        input.read_exact(&mut bytes)?;
        writeln!(output, "{}", line(&bytes))?;
    }
}
