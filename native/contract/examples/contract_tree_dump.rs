// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The parity probe of `tests/test_rust_contract_tree_parity.py`. Each line of standard input is a
//! JSON list of `[path, identity, hex bytes]` entries; the first entry is the root contract. Each line of
//! standard output is the tree or the error, as JSON.

use std::io::{self, BufRead, Write};

use archkeel_contract::policy::{assemble_tree, ContractTree, SourceProblem, TreeError, TreeIssue};
use archkeel_contract::{canonical_bytes, parse, ErrorKind};
use serde_json::{json, Value};

fn parse_kind(kind: ErrorKind) -> &'static str {
    match kind {
        ErrorKind::Invalid => "invalid",
        ErrorKind::Version => "version",
        ErrorKind::Input => "input",
        ErrorKind::DuplicateKey => "duplicate_key",
    }
}

fn issue(item: &TreeIssue) -> Value {
    json!({
        "pointer": item.pointer(),
        "parent_id": item.parent_id(),
        "path": item.path(),
        "kind": item.kind().word(),
        "reason": item.reason(),
    })
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

fn tree(tree: &ContractTree) -> Value {
    let mounts: Vec<Value> = tree
        .mounts()
        .iter()
        .map(|mount| {
            json!({
                "owner_id": mount.owner_id(),
                "parent_id": mount.parent_id(),
                "parent": mount.parent().id().as_text(),
                "pointer": mount.pointer(),
                "path": mount.path(),
                "identity": mount.identity(),
                "digest": mount.digest().as_text(),
                "canonical_digest": mount.canonical_digest().as_text(),
                "canonical": text(&canonical_bytes(mount.contract())),
            })
        })
        .collect();
    let comparison = tree.comparison();
    json!({
        "kind": "accept",
        "mounts": mounts,
        "components": comparison.components().iter().map(|c| c.id().as_text()).collect::<Vec<_>>(),
        "rules": comparison.rules().iter().map(|r| archkeel_contract::head_of(r).id().as_text()).collect::<Vec<_>>(),
        "paths": tree.paths(),
        "digest": tree.digest().as_text(),
        "comparison_digest": tree.comparison_digest().as_text(),
        "comparison": text(&canonical_bytes(comparison)),
    })
}

fn error(error: &TreeError) -> Value {
    match error {
        TreeError::UnsafeRootPath => json!({"kind": "unsafe_root"}),
        TreeError::Source(problem, paths) => {
            let word = match problem {
                SourceProblem::Unsafe => "unsafe",
                SourceProblem::Duplicate => "duplicate",
                SourceProblem::Unmounted => "unmounted",
            };
            json!({"kind": "source", "error": word, "paths": paths})
        }
        TreeError::Issues(issues) => {
            json!({"kind": "issues", "issues": issues.iter().map(issue).collect::<Vec<_>>()})
        }
    }
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

fn line(text: &str) -> Option<Value> {
    let entries: Vec<(String, String, String)> = serde_json::from_str(text).ok()?;
    let decoded: Vec<(String, String, Vec<u8>)> = entries
        .into_iter()
        .map(|(path, resolved, hex)| Some((path, resolved, unhex(&hex)?)))
        .collect::<Option<_>>()?;
    let ((root_path, _, root_bytes), rest) = decoded.split_first()?;
    let insides: Vec<(&str, &str, &[u8])> = rest
        .iter()
        .map(|(p, r, b)| (p.as_str(), r.as_str(), b.as_slice()))
        .collect();
    let root = match parse(root_bytes) {
        Ok(root) => root,
        Err(failure) => return Some(json!({"kind": "root", "error": parse_kind(failure.kind)})),
    };
    Some(match assemble_tree(root_path, root, &insides) {
        Ok(value) => tree(&value),
        Err(failure) => error(&failure),
    })
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
