// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Test only (feature `dump`): print the parse outcome of files as JSON lines.
//!
//! `archkeel-python-collector --dump <minor> <root>` reads one snapshot path a line on stdin.
//! `tests/test_collector_native_python_parse.py` compares each outcome with the failure that
//! `source.parse_sources` gives for the same bytes. `stack` is the bound of the parser stack of the
//! scan (AD-334 point 5), to measure a corpus against `MAX_STACK`. This module is not part of the
//! release binary.

use std::io::{BufRead, Write};

use archkeel_snapshot::Snapshot;
use serde_json::{json, Value};

use crate::limits::scan;
use crate::parse::parse;
use crate::pyast::{walk, Node};
use crate::source::{decode, Lines};
use crate::{discover, inputs, names, requirement};

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

/// Write one JSON line for each snapshot path on stdin; `row` gives the line, or `None` for none.
fn each_file(
    minor: &str,
    root: &str,
    mut row: impl FnMut(Option<Vec<u8>>, &str, u32) -> Option<Value>,
) -> Result<(), String> {
    let minor: u32 = minor
        .parse()
        .map_err(|_| "the dump needs a minor version")?;
    let mut snapshot = Snapshot::new(root);
    let mut out = std::io::stdout().lock();
    for line in std::io::stdin().lock().lines() {
        let rel = line.map_err(|error| format!("cannot read stdin: {error}"))?;
        if let Some(found) = row(snapshot.read(&rel), &rel, minor) {
            writeln!(out, "{found}").map_err(|error| format!("cannot write: {error}"))?;
        }
    }
    Ok(())
}

pub fn run(minor: &str, root: &str) -> Result<(), String> {
    each_file(minor, root, |raw, rel, minor| {
        let text = raw.as_deref().and_then(decode);
        let stack = text.map(|text| scan(text, &Lines::new(text), minor).stack);
        let found = outcome(raw, minor);
        Some(json!({"file": rel, "outcome": found, "stack": stack}))
    })
}

/// `--dump-texts <minor> <root>`: for each file on stdin, the class names of `ast.walk` of each
/// statement and `ast.unparse` of each expression in that order (AD-377). A failure is a marker.
pub fn texts(minor: &str, root: &str) -> Result<(), String> {
    each_file(minor, root, |raw, rel, minor| {
        let raw = raw?;
        let text = crate::source::newlines(decode(&raw)?);
        let text = text.as_ref();
        let module = parse(text, minor).ok()?;
        let mut kinds = Vec::new();
        let mut texts = Vec::new();
        let nodes = module
            .body
            .iter()
            .flat_map(|stmt| walk(Node::Stmt(stmt), minor));
        for node in nodes {
            kinds.push(node.kind());
            if let Some(expr) = node.expr() {
                texts.push(match crate::unparse::unparse(expr, minor, text) {
                    Ok(found) => found,
                    Err(failure) => format!("<{failure:?}>"),
                });
            }
        }
        Some(json!({"file": rel, "kinds": kinds, "texts": texts}))
    })
}

/// `--dump-printable <minor>`: the ranges of the code points that `str.isprintable` refuses.
pub fn printable(minor: &str) -> Result<(), String> {
    let minor: u32 = minor
        .parse()
        .map_err(|_| "--dump-printable needs a minor version")?;
    let mut ranges = Vec::new();
    let mut start: Option<u32> = None;
    for point in 0..=0x11_0000_u32 {
        let hidden = point < 0x11_0000
            && char::from_u32(point).is_none_or(|c| !crate::unparse::literal::printable(c, minor));
        match (hidden, start) {
            (true, None) => start = Some(point),
            (false, Some(low)) => {
                ranges.push(format!("{low:05X}-{:05X}", point - 1));
                start = None;
            }
            _ => {}
        }
    }
    println!("{}", ranges.join(" "));
    Ok(())
}

/// `--dump-survey`: the survey sections of one request (slices 1c-2a and 1c-2b).
pub fn survey(request: &archkeel_facts::request::PythonRequest) -> Result<Value, String> {
    let found = crate::survey::survey(request)?;
    let value = |error: serde_json::Error| error.to_string();
    Ok(json!({
        "files": serde_json::to_value(&found.files).map_err(value)?,
        "imports": serde_json::to_value(&found.imports).map_err(value)?,
        "targets": serde_json::to_value(&found.targets).map_err(value)?,
        "unknowns": serde_json::to_value(&found.unknowns).map_err(value)?,
        "coverage": serde_json::to_value(&found.coverage).map_err(value)?,
        "evidence": serde_json::to_value(&found.evidence).map_err(value)?,
    }))
}

/// `--dump-symbols <witnesses>`: the definition table of each module and the evidence that it
/// cites, or the gap of a module (AD-377). `witnesses` is `1` for the member write witnesses.
pub fn symbols(
    request: &archkeel_facts::request::PythonRequest,
    witnesses: bool,
) -> Result<Value, String> {
    let (minor, modules, binders) = crate::survey::modules(request)?;
    let mut evidence = crate::survey::module::EvidenceMap::new();
    let mut records = Vec::new();
    let mut gaps = Vec::new();
    for (module, binders) in modules.iter().zip(&binders) {
        match crate::symbols::table(
            module,
            &binders.all_exports,
            minor,
            witnesses,
            &mut evidence,
        ) {
            crate::symbols::Table::Records(found) => records.extend(found),
            crate::symbols::Table::Gap { file, reason } => {
                gaps.push(json!({"file": file, "reason": reason}));
            }
        }
    }
    records.sort_by(|left, right| left["id"].as_str().cmp(&right["id"].as_str()));
    let evidence: Vec<&archkeel_facts::envelope::Evidence> = evidence.values().collect();
    Ok(json!({
        "symbols": records,
        "evidence": serde_json::to_value(evidence).map_err(|error| error.to_string())?,
        "gaps": gaps,
    }))
}

/// `--dump-scope`: the scope of one 10.0.0 request as one JSON object (slice 1c-1).
pub fn scope(request: &archkeel_facts::request::PythonRequest) -> Result<Value, String> {
    let version = &request.resolver.interpreter.version;
    let minor: u32 = version
        .split('.')
        .nth(1)
        .and_then(|minor| minor.parse().ok())
        .ok_or_else(|| format!("the interpreter version {version} has no minor version"))?;
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let roots = &request.scope.roots;
    let found = discover::scope(&mut snapshot, roots, request.excludes_test_sources());
    let selected = found.selected;
    let namespace = &request.scope.namespace;
    let modules: serde_json::Map<String, Value> = selected
        .iter()
        .map(|rel| {
            let module = names::module_for(rel, namespace, minor);
            let package = module.as_deref().map(names::package_for);
            (rel.clone(), json!([module, package]))
        })
        .collect();
    let shadowed: Vec<Value> = names::shadowed(&selected, namespace, minor)
        .iter()
        .map(|item| {
            json!({"file": item.file, "module": item.module, "id": item.id(),
                   "title": item.title(), "message": item.message()})
        })
        .collect();
    let (inputs, source_digest) = inputs::inputs(&mut snapshot, &selected);
    let mut unseen = found.unseen;
    unseen.extend(discover::oversized(&snapshot, &selected));
    let unseen: Vec<Value> = unseen
        .iter()
        .map(|item| json!({"item": format!("{item:?}"), "reason": item.reason(&snapshot)}))
        .collect();
    let (required, state) = requirement::requirement(&mut snapshot);
    Ok(json!({
        "selected": selected,
        "modules": modules,
        "shadowed": shadowed,
        "inputs": inputs,
        "source_digest": source_digest,
        "required": required,
        "requirement_state": state.as_str(),
        "unseen": unseen,
    }))
}
