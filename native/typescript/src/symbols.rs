// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol records of PR 4.3a-3b: one `TSDEF` record for each definition
//! (`_inner_symbols`, `_symbol_metadata`, `_classifier_data`, `_attribute_declaration`,
//! `_base_record`).
//!
//! The reply does not carry them yet (AD-340). The `dump` feature prints them, and
//! `tests/test_collector_native_records.py` compares them with the unmodified Python collector.

use std::collections::HashMap;

use archkeel_wire::identity::{stable_id, Part};
use archkeel_wire::reply::Record;
use serde_json::{json, Map, Value};

use crate::definitions::DefinitionKind;
use crate::members::{Base, Member, Parameter, Visibility};
use crate::records::Cited;
use crate::source::Span;
use crate::symbol_table::{kind_value, Entry, SymbolTable};

fn visibility(item: Visibility) -> &'static str {
    match item {
        Visibility::Public => "public",
        Visibility::Protected => "protected",
        Visibility::Private => "private",
    }
}

/// The methods of each class, by the module, the name that the methods give as their parent and
/// the position of the class: Python scans all definitions for each class.
type Methods = HashMap<(String, String, i64, i64), Vec<String>>;

fn methods_of(table: &SymbolTable) -> Methods {
    let mut found = Methods::new();
    for entry in &table.entries {
        let definition = entry.definition;
        let (Some(parent), Some(line), Some(column)) = (
            entry.parent,
            definition.parent_line,
            definition.parent_column,
        ) else {
            continue;
        };
        if definition.kind == DefinitionKind::Method {
            let key = (entry.module.to_owned(), parent.to_owned(), line, column);
            found.entry(key).or_default().push(entry.id.clone());
        }
    }
    found
}

/// The records of all definitions, in the order of the table.
pub fn build(table: &SymbolTable, cited: &mut Cited) -> Vec<Record> {
    let methods = methods_of(table);
    table
        .entries
        .iter()
        .map(|entry| record(table, &methods, cited, entry))
        .collect()
}

fn is_classifier(kind: DefinitionKind) -> bool {
    matches!(
        kind,
        DefinitionKind::Class | DefinitionKind::Interface | DefinitionKind::Enum
    )
}

/// `_inner_symbols` for one definition.
fn record(table: &SymbolTable, methods: &Methods, cited: &mut Cited, entry: &Entry) -> Record {
    let definition = entry.definition;
    let evidence = cited.cite(entry.rel, &definition.span);
    let mut data = metadata(table, cited, entry);
    if matches!(
        definition.kind,
        DefinitionKind::Function | DefinitionKind::Method
    ) {
        let proven = definition.decorator_sources.is_empty();
        data.insert("signature_decorators_proven".to_owned(), json!(proven));
    }
    if is_classifier(definition.kind) {
        classifier(table, methods, cited, entry, &mut data);
    } else {
        signature(entry, &mut data);
    }
    Record {
        id: entry.id.clone(),
        evidence_class: "FACT",
        area: "source",
        kind: if is_classifier(definition.kind) {
            "class"
        } else {
            kind_value(definition.kind)
        },
        title: format!("{} declaration", entry.qualified),
        subjects: vec![entry.qualified.clone()],
        evidence_ids: vec![evidence],
        fact_ids: Vec::new(),
        data,
    }
}

/// The names and the evidence of the decorators of a definition or a member.
fn decorators(cited: &mut Cited, rel: &str, sources: &[(String, Span)]) -> (Value, Value) {
    let names: Vec<&String> = sources.iter().map(|(name, _)| name).collect();
    let evidence: Vec<String> = sources
        .iter()
        .map(|(_, span)| cited.cite(rel, span))
        .collect();
    (json!(names), json!(evidence))
}

/// `_symbol_metadata`.
fn metadata(table: &SymbolTable, cited: &mut Cited, entry: &Entry) -> Map<String, Value> {
    let definition = entry.definition;
    let parent_id = match (definition.parent_line, definition.parent_column) {
        (Some(line), Some(column)) if entry.parent.is_some() => entry
            .parent_qualified()
            .and_then(|name| table.scope(&name, line, column))
            .map(|parent| parent.id.clone()),
        _ => None,
    };
    let unknown = definition.top_level && definition.visibility.is_none();
    let kind = match definition.visibility {
        Some(item) => visibility(item),
        None if definition.top_level => "unknown",
        None => "public",
    };
    let (names, evidence) = decorators(cited, entry.rel, &definition.decorator_sources);
    let mut data = Map::new();
    data.insert("qualified_name".to_owned(), json!(entry.qualified));
    data.insert("module".to_owned(), json!(entry.module));
    data.insert("package".to_owned(), json!(entry.package()));
    data.insert("name".to_owned(), json!(definition.name));
    data.insert("parent".to_owned(), json!(entry.parent_qualified()));
    data.insert("lexical_parent_id".to_owned(), json!(parent_id));
    data.insert(
        "visibility_detail".to_owned(),
        json!({
            "kind": kind,
            "basis": if unknown { "unknown" } else { "language" },
            "spelling": definition.name,
        }),
    );
    let category = if is_classifier(definition.kind) {
        "class"
    } else {
        kind_value(definition.kind)
    };
    data.insert("symbol_category".to_owned(), json!(category));
    let unique = table.count(&entry.qualified) == 1;
    data.insert("source_binding_unique".to_owned(), json!(unique));
    data.insert("source_member_binding_static".to_owned(), json!(true));
    data.insert("class_header_static".to_owned(), json!(true));
    data.insert("decorators".to_owned(), names);
    data.insert("decorator_evidence_ids".to_owned(), evidence);
    data.insert(
        "signature_complete".to_owned(),
        json!(definition.signature_complete),
    );
    data.insert(
        "overload_signature".to_owned(),
        json!(definition.overload_signature),
    );
    data
}

/// The data of a definition that is not a class, an interface or an enum.
fn signature(entry: &Entry, data: &mut Map<String, Value>) {
    let definition = entry.definition;
    data.insert("annotation".to_owned(), json!(definition.annotation));
    data.insert("returns".to_owned(), json!(definition.returns));
    if definition.is_async {
        data.insert("async".to_owned(), json!(true));
    }
    let parameters: Vec<Value> = definition.parameters.iter().map(parameter).collect();
    data.insert("parameters".to_owned(), json!(parameters));
    if definition.kind == DefinitionKind::Method {
        let kind = if definition.is_static {
            "static"
        } else {
            "instance"
        };
        data.insert("method_kind".to_owned(), json!(kind));
    }
}

fn parameter(item: &Parameter) -> Value {
    json!({
        "name": item.name,
        "annotation": item.annotation,
        "kind": if item.rest { "varargs" } else { "positional" },
        "default": item.default,
        "default_known": item.default.is_none() && !item.optional,
    })
}

/// `_classifier_data`.
fn classifier(
    table: &SymbolTable,
    methods: &Methods,
    cited: &mut Cited,
    entry: &Entry,
    data: &mut Map<String, Value>,
) {
    let definition = entry.definition;
    match definition.kind {
        DefinitionKind::Interface => {
            data.insert("class_kind".to_owned(), json!("protocol"));
        }
        DefinitionKind::Enum => {
            data.insert("class_kind".to_owned(), json!("enum"));
        }
        _ => {}
    }
    let attributes: Vec<Value> = definition
        .members
        .iter()
        .map(|member| attribute(cited, entry, member))
        .collect();
    let attribute_ids: Vec<&Value> = attributes
        .iter()
        .map(|item| &item["definition_id"])
        .collect();
    if definition.kind == DefinitionKind::Enum {
        let names: Vec<&String> = definition
            .members
            .iter()
            .map(|member| &member.name)
            .collect();
        data.insert("enum_members".to_owned(), json!(names));
    }
    let within = match entry.parent {
        Some(parent) => format!("{parent}.{}", definition.name),
        None => definition.name.clone(),
    };
    let key = (
        entry.module.to_owned(),
        within,
        definition.span.line,
        definition.span.column,
    );
    let method_ids = methods.get(&key).cloned().unwrap_or_default();
    let complete = definition.members_complete && table.count(&entry.qualified) == 1;
    let (status, reason) = if complete {
        ("complete", Value::Null)
    } else {
        ("partial", json!("computed or unsupported member syntax"))
    };
    let inventory = |kind: &str, ids: Value| {
        json!({
            "schema_version": "1.0.0",
            "kind": kind,
            "status": status,
            "definition_ids": ids,
            "reason": reason,
        })
    };
    data.insert(
        "member_inventories".to_owned(),
        json!([
            inventory("attribute", json!(attribute_ids)),
            inventory("method", json!(method_ids)),
        ]),
    );
    let bases: Vec<Value> = definition
        .bases
        .iter()
        .map(|base| base_record(table, cited, entry, base))
        .collect();
    data.insert("base_declarations".to_owned(), json!(bases));
    data.insert("attribute_declarations".to_owned(), json!(attributes));
}

/// `_attribute_declaration`.
fn attribute(cited: &mut Cited, entry: &Entry, member: &Member) -> Value {
    let kind = member.visibility.map_or("public", visibility);
    let id = stable_id(
        "TSATTR",
        &[
            Part::Text(entry.rel),
            Part::Number(member.span.line),
            Part::Number(member.span.column),
            Part::Text(&entry.qualified),
            Part::Text(&member.name),
        ],
    );
    let evidence = cited.cite(entry.rel, &member.span);
    let (names, spans) = decorators(cited, entry.rel, &member.decorator_sources);
    json!({
        "name": member.name,
        "annotation": member.annotation,
        "visibility": {"kind": kind, "basis": "language", "spelling": member.name},
        "definition_id": id,
        "evidence_ids": [evidence],
        "decorators": names,
        "decorator_evidence_ids": spans,
        "static": member.is_static,
    })
}

/// `_base_record`.
fn base_record(table: &SymbolTable, cited: &mut Cited, entry: &Entry, base: &Base) -> Value {
    let qualified = format!("{}.{}", entry.module, base.name);
    let candidates = table.classifier_count(&qualified);
    let evidence = cited.cite(entry.rel, &base.span);
    let (status, reason) = match candidates {
        1 => ("resolved", None),
        0 => ("unresolved", Some("Base is not a unique local classifier")),
        _ => (
            "partially_resolved",
            Some("multiple classifier definition sites share the target name"),
        ),
    };
    let targets: Vec<&String> = if candidates > 0 {
        vec![&qualified]
    } else {
        Vec::new()
    };
    let id = stable_id(
        "TSBASE",
        &[
            Part::Text(&entry.qualified),
            Part::Number(base.span.line),
            Part::Number(base.span.column),
            Part::Text(&base.name),
        ],
    );
    let mut result = json!({
        "id": id,
        "relationship_kind": if base.realizes { "realizes" } else { "inherits" },
        "status": status,
        "targets": targets,
        "candidate_count": candidates,
        "candidates_truncated": false,
        "expression": base.name,
        "evidence_ids": [evidence],
    });
    if let Some(reason) = reason {
        result["reason"] = json!(reason);
    }
    result
}

#[cfg(test)]
#[path = "symbols_tests.rs"]
mod tests;
