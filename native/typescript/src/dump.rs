// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Test only (feature `dump`): print the syntax facts of files as JSON lines.
//!
//! `tests/test_collector_native_syntax.py` reads the lines and compares each field with the
//! `Syntax` that `parse.parse()` gives for the same bytes. The field names are the names of the
//! Python dataclasses. This module is not part of the release binary.

use std::collections::{BTreeSet, HashMap};
use std::io::{BufRead, Write};

use serde_json::{json, Value};

use crate::definitions::Definition;
use crate::members::{Base, Member, Parameter, Visibility};
use crate::parse::parse;
use crate::site_paths::Text;
use crate::site_syntax::ReceiverKind;
use crate::sites::{Comparison, Expression, Site, SiteKind, SiteUse};
use crate::source::Span;
use crate::source_input::classify_file;
use crate::symbol_table::kind_value;
use crate::syntax::Parsers;
use crate::walk::Syntax;
use archkeel_facts::reply::{evidence_value, target_value, Provenance};
use archkeel_wire::reply::record_value;
use archkeel_wire::request::Request;

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

fn definition(item: &Definition, parent: Option<String>) -> Value {
    json!({
        "name": item.name,
        "kind": kind_value(item.kind),
        "span": span(&item.span),
        "parent": parent,
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

fn text(item: Option<Text>, data: &[u8]) -> Value {
    json!(item.map(|item| item.decode(data)))
}

fn site_kind(item: SiteKind) -> &'static str {
    match item {
        SiteKind::Call => "call",
        SiteKind::New => "new",
        SiteKind::Reference => "reference",
    }
}

fn receiver_kind(item: ReceiverKind) -> &'static str {
    match item {
        ReceiverKind::None => "none",
        ReceiverKind::This => "this",
        ReceiverKind::Other => "other",
    }
}

/// The names that the chains of the sites hide, written once for each chain.
type Shadowed = HashMap<Option<u32>, Value>;

fn site(item: &Site, found: &Syntax, data: &[u8], shadowed: &mut Shadowed) -> Value {
    let place = item.scope.and_then(|at| found.scopes.describe(at));
    let names = shadowed
        .entry(item.shadow.chain)
        .or_insert_with(|| json!(found.sites.names.shadowed(item.shadow.chain, data)))
        .clone();
    let expression = match item.expression {
        Expression::Node(node) => node.decode(data),
        Expression::Member(receiver, name) => {
            format!("{}.{}", receiver.decode(data), name.decode(data))
        }
    };
    json!({
        "kind": site_kind(item.kind),
        "expression": expression,
        "span": span(&item.span),
        "scope": place.as_ref().map(|(name, _, _)| name),
        "scope_line": place.as_ref().map(|(_, line, _)| line),
        "assigned_name": text(item.assigned_name, data),
        "name": text(item.name, data),
        "receiver": text(item.receiver, data),
        "computed": item.computed,
        "shadowed_names": names,
        "assignment_span": item.assignment_span.as_ref().map(span),
        "assignment_annotation": item.assignment_annotation,
        "initializer": text(item.initializer, data),
        "use": match item.usage {
            SiteUse::Type => "type",
            SiteUse::Value => "value",
            SiteUse::Member => "member",
        },
        "scope_ambiguous": item.scope_ambiguous,
        "scope_column": place.as_ref().map(|(_, _, column)| column),
        "receiver_kind": receiver_kind(item.receiver_kind),
        "path": item.path.map(|path| found.sites.paths.names(path, data)).unwrap_or_default(),
        "script_free": item.script_free,
        "script_escape": item.script_escape,
    })
}

fn comparison(item: &Comparison, found: &Syntax) -> Value {
    json!({
        "span": span(&item.span),
        "scope": item.scope.map(|at| found.scopes.qualified(at)),
    })
}

/// The fields of `Syntax` that this phase produces. `data` is the text of the file, which the
/// sites cut their texts from.
pub fn syntax(found: &Syntax, data: &[u8]) -> Value {
    let mut shadowed = Shadowed::new();
    json!({
        "sites": found.sites.sites.iter().map(|item| site(item, found, data, &mut shadowed)).collect::<Vec<_>>(),
        "string_comparisons": found.sites.comparisons.iter().map(|item| comparison(item, found)).collect::<Vec<_>>(),
        "definitions": found.definitions.iter().map(|item| definition(item, found.parent_name(item))).collect::<Vec<_>>(),
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
        "script_globals": found.script.globals.iter().map(script_global).collect::<Vec<_>>(),
        "script_writes": script_writes(&found.script.writes),
        "script_aliases": found.script.aliases.iter().map(script_alias).collect::<Vec<_>>(),
        "script_factories": found.script.factories.iter().map(script_factory).collect::<Vec<_>>(),
        "script_source_writes": script_writes(&found.script.source_writes),
        "script_write_paths": found.script.write_paths,
        "script_top_level_write_paths": found.script.top_level_write_paths,
        "script_destructures": found.script.destructures.iter().map(|item| json!({
            "span": span(&item.span),
            "path": item.path,
            "members": members(&item.members),
        })).collect::<Vec<_>>(),
        "script_namespaces": found.script.namespaces.iter().map(|item| json!({
            "name": item.name,
            "span": span(&item.span),
            "initialization": span(&item.initialization),
        })).collect::<Vec<_>>(),
    })
}

fn members(items: &[crate::script_types::Member]) -> Value {
    items
        .iter()
        .map(|(published, local, at)| json!([published, local, span(at)]))
        .collect()
}

fn spans(items: &[Span]) -> Value {
    items.iter().map(span).collect()
}

fn script_writes(items: &[crate::script_types::Write]) -> Value {
    items
        .iter()
        .map(|(name, at)| json!([name, span(at)]))
        .collect()
}

/// An object with the keys in the order of the pairs.
fn object(pairs: Vec<(&str, Value)>) -> Value {
    Value::Object(
        pairs
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn script_global(item: &crate::script_types::ScriptGlobal) -> Value {
    object(vec![
        ("name", json!(item.name)),
        ("span", span(&item.span)),
        ("members", members(&item.members)),
        ("stable", json!(item.stable)),
        ("source_members", members(&item.source_members)),
        ("source_origin", json!(item.source_origin)),
        ("availability", spans(&item.availability)),
    ])
}

fn script_alias(item: &crate::script_types::ScriptAlias) -> Value {
    let mut found = serde_json::Map::new();
    found.insert("name".into(), json!(item.name));
    found.insert("span".into(), span(&item.span));
    found.insert("reference_span".into(), span(&item.reference_span));
    found.insert("path".into(), json!(item.path));
    found.insert("calls".into(), spans(&item.calls));
    found.insert("factory".into(), json!(item.factory));
    found.insert("reads".into(), spans(&item.reads));
    found.insert("escapes".into(), json!(item.escapes));
    found.insert("complete".into(), json!(item.complete));
    Value::Object(found)
}

fn script_factory(item: &crate::script_types::ScriptFactory) -> Value {
    json!({
        "name": item.name,
        "span": span(&item.span),
        "members": item.members.iter().map(|member| json!({
            "name": member.name,
            "span": span(&member.span),
            "target": member.target,
            "target_span": member.target_span.as_ref().map(span),
            "forwarded_span": member.forwarded_span.as_ref().map(span),
            "callable": member.callable,
        })).collect::<Vec<_>>(),
    })
}

/// The node kinds of `_NodeKind` that the tree of the file holds, by their names in `kinds.rs`. The
/// scaling tests use them to check that a shape holds the construct that it claims.
fn kinds(parsers: &mut Parsers, rel: &str, data: &[u8]) -> Value {
    let suffix = classify_file(rel.strip_suffix('\n').unwrap_or(rel));
    let typescript = suffix.is_some_and(|suffix| suffix.parser_typescript());
    let Some((tree, grammar)) = parsers.parse(typescript, data) else {
        return json!([]);
    };
    let mut seen = BTreeSet::new();
    let mut cursor = tree.walk();
    loop {
        seen.insert(format!("{:?}", grammar.map.of(cursor.node())));
        if cursor.goto_first_child() {
            continue;
        }
        while !cursor.goto_next_sibling() {
            if !cursor.goto_parent() {
                return json!(seen);
            }
        }
    }
}

/// Read `{"rel": ..., "file": ...}` lines from `input`. Print one `{"rel": ..., "syntax": ...}`
/// line for each, or `{"rel": ..., "error": ...}` when the file cannot be read.
pub fn run(input: impl BufRead, output: &mut impl Write) -> Result<(), String> {
    per_file(input, output, |parsers, rel, data| {
        let facts = syntax(&parse(parsers, rel, data).syntax, data);
        json!({"rel": rel, "syntax": facts, "kinds": kinds(parsers, rel, data)})
    })
}

/// The records of PR 4.3a-3a for one request: what `tests/test_collector_native_records.py`
/// compares with the Python collector.
pub fn records(request: &Request, provenance: Provenance) -> Result<Value, String> {
    let (facts, records) = crate::collect::records(request, provenance)?;
    let touched: std::collections::HashSet<&str> =
        records.touched.iter().map(String::as_str).collect();
    Ok(json!({
        "imports": records.imports,
        "targets": records.targets.iter().map(target_value).collect::<Vec<_>>(),
        "witnesses": records.witnesses.iter().map(record_value).collect::<Vec<_>>(),
        "calls": records.calls.iter().map(record_value).collect::<Vec<_>>(),
        "references": records.references.iter().map(record_value).collect::<Vec<_>>(),
        "site_bindings": records.bindings.iter().map(record_value).collect::<Vec<_>>(),
        "symbols": records.symbols.iter().map(record_value).collect::<Vec<_>>(),
        "constructs": records.constructs.iter().map(record_value).collect::<Vec<_>>(),
        "evidence": facts.evidence.iter().filter(|item| touched.contains(item.id.as_str())).map(evidence_value).collect::<Vec<_>>(),
    }))
}

/// Read `{"rel": ..., "file": ...}` lines from `input` and print the reply of `reply` for each: the
/// reply for a file that was read, or its error.
fn per_file(
    input: impl BufRead,
    output: &mut impl Write,
    mut reply: impl FnMut(&mut Parsers, &str, &[u8]) -> Value,
) -> Result<(), String> {
    let mut parsers = Parsers::new();
    for line in input.lines() {
        let line = line.map_err(|error| error.to_string())?;
        let request: Value = serde_json::from_str(&line)
            .map_err(|error| format!("dump request is not JSON: {error}"))?;
        let rel = request["rel"].as_str().unwrap_or("");
        let answer = match std::fs::read(request["file"].as_str().unwrap_or("")) {
            Ok(data) => reply(&mut parsers, rel, &data),
            Err(error) => json!({"rel": rel, "error": error.to_string()}),
        };
        writeln!(output, "{answer}").map_err(|error| error.to_string())?;
    }
    Ok(())
}

/// Read `{"rel": ..., "file": ...}` lines from `input` and print one line of counts for each file:
/// the definitions, the sites and the comparisons that the walk found. A file whose reply is
/// quadratic in the depth of its nest (the qualified name of each definition is in each record)
/// is timed with this, because it measures the walk and not the size of the reply.
pub fn count(input: impl BufRead, output: &mut impl Write) -> Result<(), String> {
    per_file(input, output, |parsers, rel, data| {
        let syntax = parse(parsers, rel, data).syntax;
        json!({
            "rel": rel,
            "definitions": syntax.definitions.len(),
            "sites": syntax.sites.sites.len(),
            "comparisons": syntax.sites.comparisons.len(),
        })
    })
}

/// Read `{"rel": ..., "file": ...}` lines from `input` and print one line for each: the name, the
/// span and the writes of the closed UMD envelope that the file is, or `null` (`umd.rs`).
pub fn umd(input: impl BufRead, output: &mut impl Write) -> Result<(), String> {
    per_file(input, output, |parsers, rel, data| {
        let found = crate::umd_publication::publication(parsers, rel, data);
        let found = found.map(
            |item| json!({"name": item.name, "span": span(&item.span), "writes": item.writes}),
        );
        json!({"rel": rel, "umd": found})
    })
}
