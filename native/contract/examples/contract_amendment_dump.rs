// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The parity probe of `tests/test_rust_contract_amendment_parity.py`. Each line of standard input
//! is one JSON object:
//!
//! - `{"op": "parse", "bytes": hex}`: read an amendment and write it again;
//! - `{"op": "gate", "before": sources or null, "path": text, "against": text, "after": sources,
//!   "amendment": hex or null}`: bind the comparison and check the amendment; `before` null is no
//!   contract at `path`;
//! - `{"op": "amend", ...the gate keys..., "decided_by": text, "rationale": text}`: write the
//!   amendment of the comparison.
//!
//! Sources are `[path, hex bytes]` pairs; the first pair is the root contract. Each line of
//! standard output is the answer, with bytes in hex.

use std::io::{self, BufRead, Write};

use archkeel_contract::parse;
use archkeel_contract::policy::{
    amendment_bytes, assemble_tree, bind, parse_amendment, AmendmentError, AmendmentField,
    Baselines, BindError, Binding, ChangeDirection, ContractTree, GateStatus, OldContract,
};
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Deserialize)]
struct Line {
    op: String,
    bytes: Option<String>,
    before: Option<Vec<(String, String)>>,
    path: Option<String>,
    against: Option<String>,
    after: Option<Vec<(String, String)>>,
    amendment: Option<String>,
    decided_by: Option<String>,
    rationale: Option<String>,
    #[serde(default)]
    baseline: bool,
}

fn unhex(text: &str) -> Option<Vec<u8>> {
    let digits: Vec<u8> = text
        .chars()
        .map(|c| c.to_digit(16).and_then(|d| u8::try_from(d).ok()))
        .collect::<Option<_>>()?;
    Some(
        digits
            .chunks(2)
            .map(|pair| pair.iter().fold(0, |a, d| a * 16 + d))
            .collect(),
    )
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn tree(pairs: &[(String, String)]) -> Option<ContractTree> {
    let decoded: Vec<(String, Vec<u8>)> = pairs
        .iter()
        .map(|(path, hex)| Some((path.clone(), unhex(hex)?)))
        .collect::<Option<_>>()?;
    let ((root_path, root_bytes), rest) = decoded.split_first()?;
    let insides: Vec<(&str, &str, &[u8])> = rest
        .iter()
        .map(|(p, b)| (p.as_str(), p.as_str(), b.as_slice()))
        .collect();
    let root = parse(root_bytes).ok()?;
    assemble_tree(root_path, root, &insides).ok()
}

fn refused(error: &AmendmentError) -> Value {
    let class = match error {
        AmendmentError::Json(_) => "json",
        AmendmentError::DuplicateKey(_) => "duplicate_key",
        AmendmentError::Version1 => "version1",
        AmendmentError::UnsupportedSchema(_) => "schema",
        _ => "field",
    };
    json!({"kind": "invalid", "class": class, "error": error.to_string()})
}

fn parsed(bytes: &[u8]) -> Value {
    match parse_amendment(bytes) {
        Ok(amendment) => json!({"kind": "parsed", "bytes": hex(&amendment_bytes(&amendment))}),
        Err(error) => refused(&error),
    }
}

/// The binding of a gate line, or the answer that refuses it: a tree that cannot be assembled,
/// or a run with a baseline (L-34a).
fn binding(line: &Line) -> Result<Binding, Value> {
    let tree_refused = || json!({"kind": "refused"});
    let after = tree(line.after.as_deref().ok_or_else(tree_refused)?).ok_or_else(tree_refused)?;
    let before = match &line.before {
        Some(sources) => Some(tree(sources).ok_or_else(tree_refused)?),
        None => None,
    };
    let old = match &before {
        Some(before) => OldContract::Tree(before),
        None => OldContract::Introduced {
            path: line.path.as_deref().ok_or_else(tree_refused)?,
            against: line.against.as_deref().ok_or_else(tree_refused)?,
        },
    };
    let baselines = if line.baseline {
        Baselines::configured_unsupported()
    } else {
        Baselines::not_configured()
    };
    bind(old, &after, baselines).map_err(|error| match error {
        BindError::BaselineNotSupported => json!({"kind": "refused", "reason": "baseline"}),
    })
}

fn gate(line: &Line) -> Option<Value> {
    let binding = match binding(line) {
        Ok(binding) => binding,
        Err(answer) => return Some(answer),
    };
    let amendment = match &line.amendment {
        Some(text) => match parse_amendment(&unhex(text)?) {
            Ok(amendment) => Some(amendment),
            Err(error) => return Some(refused(&error)),
        },
        None => None,
    };
    // The widened subject and field pairs, first seen first (Python `dict.fromkeys`).
    let mut widenings: Vec<(String, String)> = Vec::new();
    for change in binding.comparison().changes() {
        let pair = (change.subject().clone(), change.field().clone());
        if *change.direction() == ChangeDirection::Widened && !widenings.contains(&pair) {
            widenings.push(pair);
        }
    }
    let verdict = binding.check(amendment.as_ref());
    let status = match verdict.status() {
        GateStatus::Unchanged => "unchanged",
        GateStatus::Covered => "covered",
        GateStatus::Unamended => "unamended",
        GateStatus::Stale => "stale",
    };
    Some(json!({
        "kind": "gate", "status": status, "failures": verdict.failures(), "widenings": widenings,
    }))
}

fn amend(line: &Line) -> Option<Value> {
    let binding = match binding(line) {
        Ok(binding) => binding,
        Err(answer) => return Some(answer),
    };
    let written = binding.amend(line.decided_by.as_deref()?, line.rationale.as_deref()?);
    Some(match written {
        Ok(amendment) => json!({"kind": "written", "bytes": hex(&amendment_bytes(&amendment))}),
        Err(error) => refused(&error),
    })
}

/// The code points that the reader refuses as a blank `decided_by`.
fn blank_table() -> Value {
    let digest = "0".repeat(64);
    let blank: Vec<u32> = (0..=0x10_ffff_u32)
        .filter_map(char::from_u32)
        .filter(|item| {
            let document = json!({
                "schema_version": "2.0.0", "before_digest": digest, "after_digest": digest,
                "decided_by": item.to_string(), "rationale": "r",
                "before_baseline_digest": null, "after_baseline_digest": null,
            });
            let bytes = document.to_string().into_bytes();
            parse_amendment(&bytes) == Err(AmendmentError::Empty(AmendmentField::DecidedBy))
        })
        .map(u32::from)
        .collect();
    json!({ "blank": blank })
}

fn answer(text: &str) -> Option<Value> {
    let line: Line = serde_json::from_str(text).ok()?;
    match line.op.as_str() {
        "parse" => Some(parsed(&unhex(line.bytes.as_deref()?)?)),
        "gate" => gate(&line),
        "amend" => amend(&line),
        "blank_table" => Some(blank_table()),
        _ => None,
    }
}

fn main() -> io::Result<()> {
    let mut output = io::stdout().lock();
    for text in io::stdin().lock().lines() {
        let value =
            answer(&text?).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "bad line"))?;
        writeln!(output, "{value}")?;
    }
    Ok(())
}
