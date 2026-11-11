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

pub fn run(minor: &str, root: &str) -> Result<(), String> {
    let minor: u32 = minor.parse().map_err(|_| "--dump needs a minor version")?;
    let mut snapshot = Snapshot::new(root);
    let mut out = std::io::stdout().lock();
    for line in std::io::stdin().lock().lines() {
        let rel = line.map_err(|error| format!("cannot read stdin: {error}"))?;
        let raw = snapshot.read(&rel);
        let text = raw.as_deref().and_then(decode);
        let stack = text.map(|text| scan(text, &Lines::new(text), minor).stack);
        let found = outcome(raw, minor);
        let row = json!({"file": rel, "outcome": found, "stack": stack});
        writeln!(out, "{row}").map_err(|error| format!("cannot write: {error}"))?;
    }
    Ok(())
}

/// `--dump-scope`: the scope of one 10.0.0 request as one JSON object (slice 1c-1).
pub fn scope(request: &archkeel_facts::request::PythonRequest) -> Value {
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let roots = &request.scope.roots;
    let selected = discover::selected(&mut snapshot, roots, request.excludes_test_sources());
    let namespace = &request.scope.namespace;
    let modules: serde_json::Map<String, Value> = selected
        .iter()
        .map(|rel| {
            let module = names::module_for(rel, namespace);
            let package = module.as_deref().map(names::package_for);
            (rel.clone(), json!([module, package]))
        })
        .collect();
    let shadowed: Vec<Value> = names::shadowed(&selected, namespace)
        .iter()
        .map(|item| {
            json!({"file": item.file, "module": item.module, "id": item.id(),
                   "title": item.title(), "message": item.message()})
        })
        .collect();
    let (inputs, source_digest) = inputs::inputs(&mut snapshot, &selected);
    let (required, state) = requirement::requirement(&mut snapshot);
    json!({
        "selected": selected,
        "modules": modules,
        "shadowed": shadowed,
        "inputs": inputs,
        "source_digest": source_digest,
        "required": required,
        "requirement_state": state.as_str(),
    })
}
