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
use crate::resolution::{local_imports, Imports, Resolved, Resolver};
use crate::site_paths::Text;
use crate::sites::{Expression, Site, SiteKind, SiteUse};
use crate::symbol_table::SymbolTable;

/// The records of the sites in lists, for the test-only dump. The bindings are the result bindings
/// of the `new` expressions.
#[derive(Default)]
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct SiteRecords {
    pub calls: Vec<Record>,
    pub references: Vec<Record>,
    pub bindings: Vec<Record>,
}

/// The kinds of site that one pass makes records of. Python makes both in one pass and writes two
/// lists; a pass for each list writes each record when it is made. The sites of one position have
/// the order of their kinds in both orders, so the last citation of a location is the same.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Pass {
    Calls,
    References,
}

/// `_inner_sites` for one list: resolve each site of the pass and write its record. A `new`
/// expression that is assigned to a name gives a binding record, which the pass returns.
pub fn pass(
    table: &SymbolTable,
    pending: &Pending,
    imports: &Imports,
    cited: &mut Cited,
    which: Pass,
    emit: &mut dyn FnMut(Record),
) -> Vec<Record> {
    let resolver = Resolver { table, imports };
    let mut bindings = Vec::new();
    for rel in &pending.order {
        let Some(kept) = pending.kept.get(rel) else {
            continue;
        };
        for site in &kept.sites.sites {
            let reference_site = site.kind == SiteKind::Reference;
            if reference_site != (which == Pass::References) {
                continue;
            }
            let place = Place::of(table, kept, rel, site);
            let evidence = cited.cite(rel, &site.span);
            let resolved = resolver.resolve(kept, &kept.module, &place.scope, site);
            if reference_site {
                emit(reference(kept, &place, site, &resolved, evidence));
            } else {
                let (call, found) = call(table, cited, kept, &place, site, &resolved, evidence);
                emit(call);
                bindings.extend(found);
            }
        }
    }
    bindings
}

/// Both passes in lists.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub fn build(
    table: &SymbolTable,
    pending: &Pending,
    facts: &Facts,
    cited: &mut Cited,
) -> SiteRecords {
    let imports = local_imports(pending, facts);
    let mut records = SiteRecords::default();
    let calls = &mut records.calls;
    records.bindings = pass(
        table,
        pending,
        &imports,
        cited,
        Pass::Calls,
        &mut |record| {
            calls.push(record);
        },
    );
    let references = &mut records.references;
    pass(
        table,
        pending,
        &imports,
        cited,
        Pass::References,
        &mut |record| {
            references.push(record);
        },
    );
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
        let listed: Vec<Value> = values.iter().map(ResultBinding::to_json).collect();
        data.insert("result_bindings".to_owned(), json!(listed));
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

/// The name that receives a new object (`_result_binding`).
struct ResultBinding {
    id: String,
    name: String,
    annotation: Option<String>,
    initializer: String,
    evidence: String,
}

impl ResultBinding {
    fn to_json(&self) -> Value {
        json!({
            "id": self.id,
            "name": self.name,
            "target_kind": "name",
            "annotation": self.annotation,
            "initializer": self.initializer,
            "evidence_ids": [self.evidence],
            "definition_contexts": [],
        })
    }
}

/// `_result_binding`.
fn result_binding(
    cited: &mut Cited,
    kept: &Kept,
    place: &Place,
    site: &Site,
    call_id: &str,
) -> Vec<ResultBinding> {
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
    vec![ResultBinding {
        id,
        name,
        annotation: site.assignment_annotation.clone(),
        initializer: initializer.decode(data),
        evidence,
    }]
}

/// `_binding_records` for one value.
fn binding_record(place: &Place, value: &ResultBinding) -> Record {
    let mut data = Map::new();
    data.insert("module".to_owned(), json!(place.module));
    data.insert("source_scope".to_owned(), json!(place.scope));
    data.insert("source_module".to_owned(), json!(place.module));
    data.insert("binding".to_owned(), json!(value.name));
    Record {
        id: value.id.clone(),
        evidence_class: "FACT",
        area: "source",
        kind: "bindings",
        title: format!("{}.{} binding", place.scope, value.name),
        subjects: vec![place.scope.clone()],
        evidence_ids: vec![value.evidence.clone()],
        fact_ids: Vec::new(),
        data,
    }
}

#[cfg(test)]
#[path = "site_records_tests.rs"]
mod tests;
