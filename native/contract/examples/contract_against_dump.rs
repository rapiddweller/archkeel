// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The parity probe of `tests/test_rust_contract_against_parity.py`. Each line of standard input
//! is a JSON object with the lists `before` and `after` of `[path, hex bytes]` pairs; the first
//! pair of a list is its root contract. Each line of standard output is the comparison.

use std::io::{self, BufRead, Write};

use archkeel_contract::parse;
use archkeel_contract::policy::{assemble_tree, compare_trees, ChangeDirection, ContractTree};
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Deserialize)]
struct Pair {
    before: Vec<(String, String)>,
    after: Vec<(String, String)>,
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

fn line(text: &str) -> Option<Value> {
    let pair: Pair = serde_json::from_str(text).ok()?;
    let (Some(before), Some(after)) = (tree(&pair.before), tree(&pair.after)) else {
        return Some(json!({"kind": "refused"}));
    };
    let comparison = compare_trees(&before, &after);
    let changes: Vec<Value> = comparison
        .changes()
        .iter()
        .map(|change| {
            let direction = match change.direction() {
                ChangeDirection::Widened => "widened",
                ChangeDirection::Narrowed => "narrowed",
            };
            json!({
                "direction": direction,
                "subject": change.subject(),
                "field": change.field(),
                "message": change.message(),
            })
        })
        .collect();
    Some(json!({"kind": "compared", "widened": comparison.widened(), "changes": changes}))
}

fn main() -> io::Result<()> {
    let mut output = io::stdout().lock();
    for text in io::stdin().lock().lines() {
        let value =
            line(&text?).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "bad line"))?;
        writeln!(output, "{value}")?;
    }
    Ok(())
}
