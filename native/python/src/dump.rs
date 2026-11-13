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

use archkeel_facts::pyminor::PyMinor;
use archkeel_snapshot::Snapshot;
use serde_json::{json, Value};

use crate::parse::limits::scan;
use crate::parse::parse;
use crate::pyast::{walk, Node};
use crate::source::{decode, Lines};
use crate::{discover, inputs, names, requirement};

/// The explicit inputs of a source-only function; no resolver or reply assembly runs here.
pub fn facts(flag: &str, minor: &str, root: &str) -> Result<(), String> {
    each_line(minor, root, |snapshot, line, minor| {
        let input: Value = serde_json::from_str(line).map_err(|error| error.to_string())?;
        let rel = input
            .get("file")
            .and_then(Value::as_str)
            .ok_or("missing file")?;
        let table = module_table(snapshot.read(rel), rel, minor, |module| {
            use crate::bindings::FactBoundary;
            let boundary = match flag {
                "--dump-typing-signals" => FactBoundary::Typing,
                "--dump-state" => FactBoundary::State,
                _ => FactBoundary::Lexical,
            };
            crate::bindings::source_fact_table(module, minor, boundary, &input)
        });
        Ok(Some(table_row(rel, table)))
    })
}

/// The outcome of one file: `null` for a tree, else the exception, the line and the message.
fn outcome(raw: Option<Vec<u8>>, minor: PyMinor) -> Value {
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
    mut row: impl FnMut(Option<Vec<u8>>, &str, PyMinor) -> Option<Value>,
) -> Result<(), String> {
    each_line(minor, root, |snapshot, rel, minor| {
        Ok(row(snapshot.read(rel), rel, minor))
    })
}

fn each_line(
    minor: &str,
    root: &str,
    mut row: impl FnMut(&mut Snapshot, &str, PyMinor) -> Result<Option<Value>, String>,
) -> Result<(), String> {
    let minor = PyMinor::decode(minor)?;
    let mut snapshot = Snapshot::new(root);
    let mut out = std::io::stdout().lock();
    for line in std::io::stdin().lock().lines() {
        let rel = line.map_err(|error| format!("cannot read stdin: {error}"))?;
        if let Some(found) = row(&mut snapshot, &rel, minor)? {
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

/// The binding inputs of a file before import convergence, or a named incomplete-file gap.
pub fn bindings(minor: &str, root: &str, proofs: bool) -> Result<(), String> {
    each_file(minor, root, |raw, rel, minor| {
        let table = module_table(raw, rel, minor, |module| {
            if proofs {
                crate::bindings::proof_table(module, minor)
            } else {
                crate::bindings::table(module, minor)
            }
        });
        Some(table_row(rel, table))
    })
}

fn module_table(
    raw: Option<Vec<u8>>,
    rel: &str,
    minor: PyMinor,
    collect: impl FnOnce(&crate::module::Module) -> crate::bindings::Table,
) -> crate::bindings::Table {
    let found = (|| {
        let text = raw.as_deref().and_then(decode).ok_or("source unreadable")?;
        let text = crate::source::newlines(text).into_owned();
        let tree = parse(&text, minor).map_err(|failure| failure.message)?;
        let first = rel.split('/').next().unwrap_or(rel);
        let namespace = first.strip_suffix(".py").unwrap_or(first);
        let name = names::module_for(rel, namespace, minor).ok_or("module name unseen")?;
        Ok::<_, String>(crate::module::Module::new(rel.to_owned(), name, text, tree))
    })();
    match found {
        Ok(module) => collect(&module),
        Err(reason) => crate::bindings::Table {
            data: Err(reason),
            work: 0,
        },
    }
}

fn table_row(rel: &str, table: crate::bindings::Table) -> Value {
    let crate::bindings::Table { data, work } = table;
    let row = match data {
        Ok(data) => Value::Object(serde_json::Map::from_iter([
            ("file".into(), json!(rel)),
            ("full_scope".into(), Value::Bool(true)),
            ("work".into(), json!(work)),
            ("data".into(), data),
        ])),
        Err(reason) => json!({"file": rel, "full_scope": false, "gap": reason, "work": work}),
    };
    match crate::bindings::check_output(&row) {
        Ok(()) => row,
        Err(reason) => {
            let gap = json!({"file": rel, "full_scope": false, "gap": reason, "work": work});
            if crate::bindings::check_output(&gap).is_ok() {
                gap
            } else {
                json!({"file": null, "full_scope": false, "gap": reason, "work": work})
            }
        }
    }
}

/// `--dump-texts <minor> <root>`: for each file on stdin, the class names of `ast.walk` of each
/// statement and `ast.unparse` of each expression in that order (AD-377). A failure is a marker.
pub fn texts(minor: &str, root: &str) -> Result<(), String> {
    each_file(minor, root, |raw, rel, minor| {
        let Some(source) = raw.as_deref().and_then(decode) else {
            return Some(json!({"file": rel, "gap": outcome(raw, minor)}));
        };
        let text = crate::source::newlines(source);
        let text = text.as_ref();
        let module = match parse(text, minor) {
            Ok(module) => module,
            Err(failure) => {
                return Some(json!({"file": rel, "gap": {
                    "exception": failure.exception.as_str(), "line": failure.line, "message": failure.message,
                }}))
            }
        };
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
    let minor = PyMinor::decode(minor)?;
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
    let crate::survey::Modules {
        minor,
        modules,
        binders,
        gaps: parse_gaps,
    } = crate::survey::modules(request)?;
    let mut evidence = crate::module::EvidenceMap::new();
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
        "parse_gaps": serde_json::to_value(parse_gaps).map_err(|error| error.to_string())?,
    }))
}

/// `--dump-scope`: the scope of one 10.0.0 request as one JSON object (slice 1c-1).
pub fn scope(request: &archkeel_facts::request::PythonRequest) -> Result<Value, String> {
    let minor = request.resolver.interpreter.version.minor();
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
