// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The edges of the symbol table (AD-498): the call, reference, base and construction sites,
//! and the value bindings of call results.
//!
//! Reference engine: `ir/source_graph.py` `_relationships`, `_site_relationship`, `_endpoint`,
//! `_source_endpoint`, `_value_bindings` and `_construction_sites` at release 4.0.1. A site is
//! resolved only with the status `resolved` and one target entity. A name that no record defines
//! is a referenced entity, which a defined target never matches.

use archkeel_contract::{EntityKind, RelationshipKind, ResolutionKind};
use archkeel_facts::data::{CallData, ReferenceData};
use archkeel_facts::envelope::Facts;
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::Status;
use archkeel_facts::{CallFact, Record, ReferenceFact, Section, SymbolFact};

use crate::symbols::{evidence, parse, Edge, Entity, Symbols};

/// The parts of one site record that `_site_relationship` reads.
struct Site<'r> {
    kind: RelationshipKind,
    source: String,
    names: &'r [String],
    status: Status,
    count: Option<i64>,
    evidence: Vec<String>,
}

/// Add the edges of the calls, the references and the bases to the table.
pub(crate) fn sites(table: &mut Symbols, facts: &Facts, symbols: &[Record<SymbolFact>]) {
    for section in &facts.sections {
        if let Section::Calls(records) = section {
            for record in records {
                call(table, record);
            }
        }
    }
    for section in &facts.sections {
        if let Section::References(records) = section {
            for record in records {
                reference(table, record);
            }
        }
    }
    for record in symbols {
        if let SymbolFact::Class(data) = &record.data {
            let mut resolved = true;
            for base in &data.base_declarations {
                let Some(kind) = parse::<RelationshipKind>(base.relationship_kind.as_str()) else {
                    table.refuse("a base has no relationship kind");
                    continue;
                };
                resolved &= base.status == Status::Resolved;
                let site = Site {
                    kind,
                    source: record.id.as_str().to_owned(),
                    names: &base.targets,
                    status: base.status,
                    count: Some(base.candidate_count),
                    evidence: evidence(&base.evidence_ids),
                };
                edge(table, site);
            }
            table.bases.insert(record.id.as_str().to_owned(), resolved);
        }
    }
}

fn call(table: &mut Symbols, record: &Record<CallFact>) {
    let data: &CallData = match &record.data {
        CallFact::Calls(data)
        | CallFact::Call(data)
        | CallFact::ResolvedCall(data)
        | CallFact::PartiallyResolvedCall(data)
        | CallFact::UnresolvedCall(data) => data,
    };
    let Some(source) = source(
        table,
        record.id.as_str(),
        &data.source_scope,
        &data.source_definition_id,
    ) else {
        return;
    };
    let site = Site {
        kind: RelationshipKind::Calls,
        source: source.clone(),
        names: &data.targets,
        status: data.status,
        count: Some(data.candidate_count),
        evidence: evidence(&record.evidence_ids),
    };
    edge(table, site);
    let bindings = match &data.result_bindings {
        Some(sites) => crate::symbol_values::bindings(table, &source, sites, &record.evidence_ids),
        None => Vec::new(),
    };
    if let Nullable::Value(found) = &data.construction {
        let cited = (source.as_str(), record.evidence_ids.as_slice());
        crate::symbol_values::construction(table, (data, found), cited, &bindings);
    }
}

fn reference(table: &mut Symbols, record: &Record<ReferenceFact>) {
    let id = record.id.as_str();
    let (scope, names, status, count, definition) = match &record.data {
        ReferenceFact::SourceRole(data) => {
            (&data.source_scope, &data.targets, data.status, None, None)
        }
        ReferenceFact::References(data)
        | ReferenceFact::Reference(data)
        | ReferenceFact::ScriptNamespaceEffect(data)
        | ReferenceFact::ValueReference(data)
        | ReferenceFact::AttributeReference(data) => (
            &data.source_scope,
            &data.targets,
            data.status,
            data.candidate_count,
            Some(data),
        ),
    };
    let absent = Nullable::Absent;
    let declared = definition.map_or(&absent, |data| &data.source_definition_id);
    let Some(mut source) = source(table, id, scope, declared) else {
        return;
    };
    if let Some(data) = definition {
        match declaration(table, data, &source) {
            Ok(Some(found)) => source = found,
            Ok(None) => {}
            Err(why) => return table.refuse(why),
        }
    }
    let site = Site {
        kind: RelationshipKind::References,
        source,
        names,
        status,
        count,
        evidence: evidence(&record.evidence_ids),
    };
    edge(table, site);
}

/// `_declaration_endpoint`: the operation that a reference declares, when it names one.
fn declaration(
    table: &Symbols,
    data: &ReferenceData,
    owner: &str,
) -> Result<Option<String>, &'static str> {
    match (&data.declaration_scope, &data.declaration_definition_id) {
        (None, None) => Ok(None),
        (Some(scope), Some(identity)) => {
            let found = table.resolving(scope).into_iter().any(|index| {
                let entity = &table.entities[index];
                entity.id == identity.as_str()
                    && matches!(entity.kind, EntityKind::Method | EntityKind::Function)
                    && entity.parent.as_deref() == Some(owner)
            });
            if found {
                Ok(Some(identity.as_str().to_owned()))
            } else {
                Err("a reference declaration matches no operation")
            }
        }
        _ => Err("a reference declaration needs a scope and a definition id"),
    }
}

/// `_source_endpoint`: the entity of the scope of a site.
fn source(
    table: &mut Symbols,
    record: &str,
    name: &str,
    declared: &Nullable<archkeel_facts::ids::FactId>,
) -> Option<String> {
    match declared {
        Nullable::Value(identity) => {
            if table.named(name).iter().any(|id| id == identity.as_str()) {
                Some(identity.as_str().to_owned())
            } else {
                table.refuse("a source definition does not match its scope");
                None
            }
        }
        // A missing declaration does not borrow another definition with the same name.
        Nullable::Null => {
            let id = format!("refscope:{record}");
            let mut entity = Entity::named(id.clone(), EntityKind::Symbol, name, Vec::new());
            entity.defined = false;
            table.insert(entity, false);
            Some(id)
        }
        Nullable::Absent => {
            let found = endpoint(table, name);
            if found.len() == 1 {
                found.into_iter().next()
            } else {
                table.refuse("an ambiguous source scope has no definition id");
                None
            }
        }
    }
}

/// `_endpoint`: the entities named `name`, or one new referenced entity.
pub(crate) fn endpoint(table: &mut Symbols, name: &str) -> Vec<String> {
    let known = table.named(name);
    if !known.is_empty() {
        return known;
    }
    let id = format!("ref:{name}");
    let mut entity = Entity::named(id.clone(), EntityKind::Symbol, name, Vec::new());
    entity.defined = false;
    table.insert(entity, true);
    vec![id]
}

/// `_site_relationship`: one edge of a site. The targets are the entities of each name, once.
fn edge(table: &mut Symbols, site: Site<'_>) {
    let mut targets: Vec<String> = Vec::new();
    for name in site.names {
        for id in endpoint(table, name) {
            if !targets.contains(&id) {
                targets.push(id);
            }
        }
    }
    let Some(status) = resolution(site.status) else {
        return table.refuse("a site has no resolution status");
    };
    let names = i64::try_from(site.names.len()).unwrap_or(i64::MAX);
    if site.count.is_some_and(|count| count < names) {
        return table.refuse("a candidate count is smaller than its targets");
    }
    if status == ResolutionKind::Unresolved && !targets.is_empty() {
        return table.refuse("an unresolved site has candidates");
    }
    let resolved = status == ResolutionKind::Resolved && targets.len() == 1;
    table.edges.push(Edge {
        kind: site.kind,
        source: site.source,
        target: resolved.then(|| targets.remove(0)),
        resolution: if resolved {
            ResolutionKind::Resolved
        } else if status == ResolutionKind::Unresolved {
            ResolutionKind::Unresolved
        } else {
            ResolutionKind::Partial
        },
        evidence: site.evidence,
    });
}

/// The resolution of a recorded status, or `None` when 4.0.1 has none for it.
pub(crate) fn resolution(status: Status) -> Option<ResolutionKind> {
    match status {
        Status::Resolved => Some(ResolutionKind::Resolved),
        Status::PartiallyResolved => Some(ResolutionKind::Partial),
        Status::Unresolved => Some(ResolutionKind::Unresolved),
        Status::Unknown | Status::Decided => None,
    }
}
