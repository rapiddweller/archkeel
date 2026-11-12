// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Baseline parity probe: each input line is a JSON string of hex bytes (AD-386).

use std::io::{self, BufRead, Write};

use archkeel_contract::policy::{baseline_bytes, baseline_digest, parse_baseline, BaselineError};
use serde_json::{json, Value};

fn unhex(text: &str) -> Option<Vec<u8>> {
    if !text.len().is_multiple_of(2) {
        return None;
    }
    text.as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let high = char::from(*pair.first()?).to_digit(16)?;
            let low = char::from(*pair.get(1)?).to_digit(16)?;
            u8::try_from(high * 16 + low).ok()
        })
        .collect()
}

fn answer(bytes: &[u8]) -> Value {
    match parse_baseline(bytes) {
        Ok(baseline) => {
            let written: String = baseline_bytes(&baseline)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect();
            json!({"kind": "parsed", "value": baseline, "bytes": written, "digest": baseline_digest(&baseline)})
        }
        Err(error) => {
            let class = match &error {
                BaselineError::Json(_) => "json",
                BaselineError::DuplicateKey(_) => "duplicate_key",
                BaselineError::TooLarge => "size",
                BaselineError::IntegerRange(_) => "integer_range",
                BaselineError::UnsupportedSchema(_) => "schema",
                _ => "field",
            };
            json!({"kind": "invalid", "class": class, "error": error.to_string()})
        }
    }
}

fn main() -> io::Result<()> {
    let mut output = io::stdout().lock();
    for line in io::stdin().lock().lines() {
        let text: String = serde_json::from_str(&line?)?;
        let bytes =
            unhex(&text).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "bad hex"))?;
        writeln!(output, "{}", answer(&bytes))?;
    }
    Ok(())
}
