// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Test only (feature `dump`): print the parse outcome of files as JSON lines.
//!
//! `archkeel-python-collector --dump <minor> <root>` reads one snapshot path a line on stdin.
//! `tests/test_collector_native_python_parse.py` compares each outcome with the failure that
//! `source.parse_sources` gives for the same bytes. This module is not part of the release binary.

use std::io::{BufRead, Write};

use archkeel_snapshot::Snapshot;
use serde_json::{json, Value};

use crate::parse::parse;
use crate::source::decode;

/// The outcome of one file: `null` for a tree, else the exception, the line and the message.
fn outcome(raw: Option<Vec<u8>>, minor: u32) -> Value {
    let Some(raw) = raw else {
        return json!({"exception": "OSError", "line": 1, "message": "unreadable"});
    };
    let Some(text) = decode(&raw) else {
        return json!({"exception": "UnicodeDecodeError", "line": 1, "message": "UnicodeDecodeError"});
    };
    match parse(text, minor) {
        Ok(_) => Value::Null,
        Err(failure) => json!({
            "exception": failure.exception.as_str(),
            "line": failure.line,
            "message": failure.message,
        }),
    }
}

pub fn run(minor: &str, root: &str) -> Result<(), String> {
    let minor: u32 = minor.parse().map_err(|_| "--dump needs a minor version")?;
    let mut snapshot = Snapshot::new(root);
    let mut out = std::io::stdout().lock();
    for line in std::io::stdin().lock().lines() {
        let rel = line.map_err(|error| format!("cannot read stdin: {error}"))?;
        let found = outcome(snapshot.read(&rel), minor);
        let row = json!({"file": rel, "outcome": found});
        writeln!(out, "{row}").map_err(|error| format!("cannot write: {error}"))?;
    }
    Ok(())
}
