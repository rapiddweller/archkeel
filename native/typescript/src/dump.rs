// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Test only (feature `dump`): print the syntax facts of files as JSON lines.
//!
//! `tests/test_collector_native_syntax.py` reads the lines and compares each field with the
//! `Syntax` that `parse.parse()` gives for the same bytes. The field names are the names of the
//! Python dataclasses. This module is not part of the release binary.

use std::io::{BufRead, Write};

use serde_json::{json, Value};

use crate::definitions::{Definition, DefinitionKind};
use crate::members::{Base, Member, Parameter, Visibility};
use crate::parse::parse;
use crate::syntax::{Parsers, Span};
use crate::walk::Syntax;

fn span(span: &Span) -> Value {
    json!({
        "line": span.line,
        "end_line": span.end_line,
        "column": span.column,
        "excerpt": span.excerpt,
    })
}

fn named_spans(items: &[(String, Span)]) -> Value {
    items
        .iter()
        .map(|(name, at)| json!([name, span(at)]))
        .collect()
}

fn parameter(item: &Parameter) -> Value {
    json!({
        "name": item.name,
        "annotation": item.annotation,
        "optional": item.optional,
        "rest": item.rest,
        "default": item.default,
    })
}

fn member(item: &Member) -> Value {
    json!({
        "name": item.name,
        "span": span(&item.span),
        "annotation": item.annotation,
        "visibility": visibility(item.visibility),
        "static": item.is_static,
        "literal": item.literal,
        "decorator_sources": named_spans(&item.decorator_sources),
    })
}

fn base(item: &Base) -> Value {
    json!({
        "name": item.name,
        "relationship": if item.realizes { "realizes" } else { "inherits" },
        "span": span(&item.span),
    })
}

fn visibility(item: Option<Visibility>) -> Value {
    json!(item.map(|item| match item {
        Visibility::Public => "public",
        Visibility::Protected => "protected",
        Visibility::Private => "private",
    }))
}

fn kind(item: DefinitionKind) -> &'static str {
    match item {
        DefinitionKind::Class => "class",
        DefinitionKind::Interface => "interface",
        DefinitionKind::Enum => "enum",
        DefinitionKind::Method => "method",
        DefinitionKind::Function => "function",
        DefinitionKind::TypeAlias => "type_alias",
        DefinitionKind::Constant => "constant",
    }
}

fn definition(item: &Definition) -> Value {
    json!({
        "name": item.name,
        "kind": kind(item.kind),
        "span": span(&item.span),
        "parent": item.parent,
        "visibility": visibility(item.visibility),
        "static": item.is_static,
        "exported": item.exported,
        "annotation": item.annotation,
        "parameters": item.parameters.iter().map(parameter).collect::<Vec<_>>(),
        "returns": item.returns,
        "bases": item.bases.iter().map(base).collect::<Vec<_>>(),
        "members": item.members.iter().map(member).collect::<Vec<_>>(),
        "decorators": item.decorators,
        "abstract": item.is_abstract,
        "members_complete": item.members_complete,
        "overload_signature": item.overload_signature,
        "top_level": item.top_level,
        "signature_complete": item.signature_complete,
        "parent_line": item.parent_line,
        "parent_column": item.parent_column,
        "is_async": item.is_async,
        "decorator_sources": named_spans(&item.decorator_sources),
    })
}

/// The fields of `Syntax` that this phase produces.
pub fn syntax(found: &Syntax) -> Value {
    json!({
        "definitions": found.definitions.iter().map(definition).collect::<Vec<_>>(),
        "import_bindings": found.import_bindings.iter().map(|item| json!({
            "span": span(&item.span),
            "imported": item.imported,
            "local": item.local,
            "namespace": item.namespace,
            "type_only": item.type_only,
            "source_unique": item.source_unique,
        })).collect::<Vec<_>>(),
        "module_exports": found.module_exports.iter()
            .map(|(name, declaration, export)| json!([name, span(declaration), span(export)]))
            .collect::<Vec<_>>(),
        "rebound_names": found.rebound_names,
        "ambient_globals": named_spans(&found.ambient_globals),
        "ambient_top_level": named_spans(&found.ambient_top_level),
        "module_file": found.module_file,
        "declaration_file": found.declaration_file,
        "script_mode": found.script_mode,
        "script_bindings": found.script_bindings,
    })
}

/// Read `{"rel": ..., "file": ...}` lines from `input`. Print one `{"rel": ..., "syntax": ...}`
/// line for each, or `{"rel": ..., "error": ...}` when the file cannot be read.
pub fn run(input: impl BufRead, output: &mut impl Write) -> Result<(), String> {
    let mut parsers = Parsers::new();
    for line in input.lines() {
        let line = line.map_err(|error| error.to_string())?;
        let request: Value = serde_json::from_str(&line)
            .map_err(|error| format!("dump request is not JSON: {error}"))?;
        let rel = request["rel"].as_str().unwrap_or("");
        let reply = match std::fs::read(request["file"].as_str().unwrap_or("")) {
            Ok(data) => {
                json!({"rel": rel, "syntax": syntax(&parse(&mut parsers, rel, &data).syntax)})
            }
            Err(error) => json!({"rel": rel, "error": error.to_string()}),
        };
        writeln!(output, "{reply}").map_err(|error| error.to_string())?;
    }
    Ok(())
}
