// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The call, reference and binding records of PR 4.3a-3c (`_inner_sites`, `_reference_record`,
//! `_call_record`, `_binding_records`, `_result_binding`).
//!
//! The reply does not carry them yet (AD-340). The `dump` feature prints them, and
//! `tests/test_collector_native_records.py` compares them with the unmodified Python collector.

use archkeel_wire::identity::{stable_id, Part};
use archkeel_wire::reply::{Facts, Record};
use serde_json::{json, Map, Value};

use crate::cited::Cited;
use crate::kept::{Kept, Pending};
use crate::resolution::{local_imports, Resolved, Resolver};
use crate::site_paths::Text;
use crate::sites::{Expression, Site, SiteKind, SiteUse};
use crate::symbol_table::SymbolTable;

/// The records of the sites, in the order of Python: files in the order of the walk, sites by
/// position. The bindings are the result bindings of the `new` expressions.
#[derive(Default)]
pub struct SiteRecords {
    pub calls: Vec<Record>,
    pub references: Vec<Record>,
    pub bindings: Vec<Record>,
}

/// `_inner_sites`: resolve each site and make its record.
pub fn build(
    table: &SymbolTable,
    pending: &Pending,
    facts: &Facts,
    cited: &mut Cited,
) -> SiteRecords {
    let imports = local_imports(pending, facts);
    let resolver = Resolver {
        table,
        imports: &imports,
    };
    let mut records = SiteRecords::default();
    for rel in &pending.order {
        let Some(kept) = pending.kept.get(rel) else {
            continue;
        };
        for site in &kept.sites.sites {
            let place = Place::of(table, kept, rel, site);
            let evidence = cited.cite(rel, &site.span);
            let resolved = resolver.resolve(kept, &kept.module, &place.scope, site);
            if site.kind == SiteKind::Reference {
                let record = reference(kept, &place, site, &resolved, evidence);
                records.references.push(record);
            } else {
                let (call, bindings) = call(table, cited, kept, &place, site, &resolved, evidence);
                records.calls.push(call);
                records.bindings.extend(bindings);
            }
        }
    }
    records
}

/// Where a site stands: the file, the qualified scope and the id of the definition that holds it.
struct Place<'a> {
    rel: &'a str,
    module: &'a str,
    scope: String,
    source_id: Option<String>,
}

impl<'a> Place<'a> {
    fn of(table: &SymbolTable, kept: &'a Kept, rel: &'a str, site: &Site) -> Self {
        let described = site.scope.and_then(|at| kept.scopes.describe(at));
        let module = kept.module.as_str();
        let scope = match &described {
            Some((name, _, _)) if !name.is_empty() => format!("{module}.{name}"),
            _ => module.to_owned(),
        };
        let source_id = described
            .and_then(|(_, line, column)| table.scope(&scope, line, column))
            .map(|entry| entry.id.clone());
        Self {
            rel,
            module,
            scope,
            source_id,
        }
    }
}

fn expression(kept: &Kept, site: &Site) -> String {
    let data = kept.text.as_bytes();
    match site.expression {
        Expression::Node(node) => node.decode(data),
        Expression::Member(receiver, name) => {
            format!("{}.{}", receiver.decode(data), name.decode(data))
        }
    }
}

/// The fields that a reference and a call share.
fn common(
    kept: &Kept,
    place: &Place,
    site: &Site,
    resolved: &Resolved,
) -> (String, Map<String, Value>) {
    let expression = expression(kept, site);
    let mut data = Map::new();
    data.insert("source_scope".to_owned(), json!(place.scope));
    data.insert("source_module".to_owned(), json!(place.module));
    data.insert("expression".to_owned(), json!(expression));
    data.insert("status".to_owned(), json!(resolved.status));
    data.insert("targets".to_owned(), json!(resolved.candidates));
    data.insert(
        "candidate_count".to_owned(),
        json!(resolved.candidates.len()),
    );
    data.insert("candidates_truncated".to_owned(), json!(false));
    (expression, data)
}

/// The reason and the id of the definition, written after the fields above (`if reason:`).
fn finish(data: &mut Map<String, Value>, place: &Place, resolved: &Resolved) {
    if let Some(reason) = resolved.reason.filter(|reason| !reason.is_empty()) {
        data.insert("reason".to_owned(), json!(reason));
    }
    if let Some(id) = &place.source_id {
        data.insert("source_definition_id".to_owned(), json!(id));
    }
}

fn subjects(place: &Place, resolved: &Resolved) -> Vec<String> {
    let mut found = vec![place.scope.clone()];
    found.extend(resolved.candidates.iter().cloned());
    found.retain(|value| !value.is_empty());
    found.sort();
    found
}

/// `_reference_record`.
fn reference(
    kept: &Kept,
    place: &Place,
    site: &Site,
    resolved: &Resolved,
    evidence: String,
) -> Record {
    let (expression, mut data) = common(kept, place, site, resolved);
    let usage = match site.usage {
        SiteUse::Type => "type",
        SiteUse::Value => "value",
        SiteUse::Member => "member",
    };
    data.insert("use".to_owned(), json!(usage));
    finish(&mut data, place, resolved);
    let id = stable_id(
        "TSREF",
        &[
            Part::Text(place.module),
            Part::Number(site.span.line),
            Part::Number(site.span.column),
            Part::Text(&expression),
        ],
    );
    Record {
        id,
        evidence_class: "FACT",
        area: "source",
        kind: "references",
        title: expression,
        subjects: subjects(place, resolved),
        evidence_ids: vec![evidence],
        fact_ids: Vec::new(),
        data,
    }
}

/// `_call_record`: the record, and the binding records of a `new` expression.
fn call(
    table: &SymbolTable,
    cited: &mut Cited,
    kept: &Kept,
    place: &Place,
    site: &Site,
    resolved: &Resolved,
    evidence: String,
) -> (Record, Vec<Record>) {
    let (expression, mut data) = common(kept, place, site, resolved);
    let id = stable_id(
        "TSCALL",
        &[
            Part::Text(place.module),
            Part::Number(site.span.line),
            Part::Number(site.span.column),
            Part::Text(&expression),
        ],
    );
    finish(&mut data, place, resolved);
    let mut bindings = Vec::new();
    if site.kind == SiteKind::New {
        data.insert("construction".to_owned(), construction(table, resolved));
        let values = result_binding(cited, kept, place, site, &id);
        bindings = values
            .iter()
            .map(|value| binding_record(place, value))
            .collect();
        data.insert("result_bindings".to_owned(), json!(values));
    }
    let record = Record {
        id,
        evidence_class: "FACT",
        area: "source",
        kind: "calls",
        title: expression,
        subjects: subjects(place, resolved),
        evidence_ids: vec![evidence],
        fact_ids: Vec::new(),
        data,
    };
    (record, bindings)
}

/// The `construction` of a `new` expression: the targets that are classes.
fn construction(table: &SymbolTable, resolved: &Resolved) -> Value {
    let targets: Vec<&String> = resolved
        .candidates
        .iter()
        .filter(|target| table.class_count(target) > 0)
        .collect();
    let status = if targets.len() == 1 && resolved.status == "resolved" {
        "resolved"
    } else if targets.is_empty() {
        "unresolved"
    } else {
        "partially_resolved"
    };
    let reason = if status == "resolved" {
        "Unique local classifier construction"
    } else {
        resolved
            .reason
            .filter(|reason| !reason.is_empty())
            .unwrap_or("Construction target is not proven")
    };
    json!({
        "status": status,
        "targets": targets,
        "candidates_truncated": false,
        "reason": reason,
    })
}

/// `_result_binding`: the name that receives the new object.
fn result_binding(
    cited: &mut Cited,
    kept: &Kept,
    place: &Place,
    site: &Site,
    call_id: &str,
) -> Vec<Value> {
    let data = kept.text.as_bytes();
    let name = site.assigned_name.map(|text| text.decode(data));
    let initializer = site.initializer.filter(|text| !Text::is_empty(*text));
    let (Some(name), Some(span), Some(initializer)) = (
        name.filter(|name| !name.is_empty()),
        &site.assignment_span,
        initializer,
    ) else {
        return Vec::new();
    };
    let id = stable_id(
        "VALUEBIND",
        &[
            Part::Text(call_id),
            Part::Number(span.line),
            Part::Number(span.column),
            Part::Text(&name),
        ],
    );
    let evidence = cited.cite(place.rel, span);
    vec![json!({
        "id": id,
        "name": name,
        "target_kind": "name",
        "annotation": site.assignment_annotation,
        "initializer": initializer.decode(data),
        "evidence_ids": [evidence],
        "definition_contexts": [],
    })]
}

/// `_binding_records` for one value.
fn binding_record(place: &Place, value: &Value) -> Record {
    let name = value["name"].as_str().unwrap_or("");
    let mut data = Map::new();
    data.insert("module".to_owned(), json!(place.module));
    data.insert("source_scope".to_owned(), json!(place.scope));
    data.insert("source_module".to_owned(), json!(place.module));
    data.insert("binding".to_owned(), json!(name));
    let evidence: Vec<String> = value["evidence_ids"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|item| item.as_str().map(str::to_owned))
        .collect();
    Record {
        id: value["id"].as_str().unwrap_or("").to_owned(),
        evidence_class: "FACT",
        area: "source",
        kind: "bindings",
        title: format!("{}.{name} binding", place.scope),
        subjects: vec![place.scope.clone()],
        evidence_ids: evidence,
        fact_ids: Vec::new(),
        data,
    }
}

#[cfg(test)]
#[path = "site_records_tests.rs"]
mod tests;
