// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The call, reference and binding records of PR 4.3a-3c (`_inner_sites`, `_reference_record`,
//! `_call_record`, `_binding_records`, `_result_binding`).
//!
//! The reply carries them under the capability `inner-uml-v1` (AD-340). The `dump` feature prints them, and
//! `tests/test_collector_native_records.py` compares them with the unmodified Python collector.

use archkeel_facts::data::{BindingData, CallData, ReferenceData};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName};
use archkeel_facts::nested::{Construction, ResultBinding};
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::{Area, EvidenceClass, Status, Use};
use archkeel_facts::{BindingFact, CallFact, Record, ReferenceFact};
use archkeel_wire::stream::TypedEmit;

use crate::cited::Cited;
use crate::kept::{Kept, Pending};
use crate::resolution::{Imports, Resolved, Resolver};
use crate::script_records::SiteKey;
use crate::site_paths::Text;
use crate::sites::{Expression, Site, SiteKind, SiteUse};
use crate::symbol_table::SymbolTable;

/// The records that one pass writes, and where they go. Python makes both in one pass and writes
/// two lists; a pass for each list writes each record when it is made. The sites of one position
/// have the order of their kinds in both orders, so the last citation of a location is the same.
pub enum Pass<'e> {
    Calls(TypedEmit<'e, CallFact>),
    References(TypedEmit<'e, ReferenceFact>),
}

/// A binding record and the place of its site (the file and the site in the file), so that the
/// bindings of the two passes come in the order of the sites, as Python makes them in one pass.
pub type Placed = ((usize, usize), Record<BindingFact>);

/// `_inner_sites` for one list: resolve each site of the pass and write its record. A `new`
/// expression that is assigned to a name gives a binding record, and so does the alias that a
/// script reference initializes; the pass returns them.
pub fn pass(
    table: &SymbolTable,
    pending: &Pending,
    imports: &Imports,
    cited: &mut Cited,
    mut out: Pass<'_>,
) -> Vec<Placed> {
    let resolver = Resolver { table, imports };
    let mut bindings = Vec::new();
    for (file_at, rel) in pending.order.iter().enumerate() {
        let Some(kept) = pending.kept.get(rel) else {
            continue;
        };
        let scripted = pending.script.modules.get(&kept.module);
        for (site_at, site) in kept.sites.sites.iter().enumerate() {
            let reference_site = site.kind == SiteKind::Reference;
            if reference_site != matches!(out, Pass::References(_)) {
                continue;
            }
            let place = Place::of(table, kept, rel, site);
            let evidence = cited.cite(rel, &site.span);
            let key = scripted.map(|_| site_key(kept, site));
            let proofs = scripted.zip(key.as_ref());
            let targets = proofs.and_then(|(found, key)| found.resolution.get(key));
            let resolved = resolver.resolve(
                kept,
                &kept.module,
                &place.scope,
                site,
                targets.map(Vec::as_slice),
            );
            let proven =
                proofs.map(|(found, key)| (found.evidence.get(key), found.fact_ids.get(key)));
            let found = match &mut out {
                Pass::References(emit) => {
                    let mut record = reference(kept, &place, site, &resolved, evidence);
                    let alias = prove(kept, &place, site, &mut record, proven);
                    emit(&record);
                    alias
                }
                Pass::Calls(emit) => {
                    let (mut record, values) =
                        call(table, cited, kept, &place, site, &resolved, evidence);
                    let alias = prove(kept, &place, site, &mut record, proven);
                    emit(&record);
                    values.into_iter().chain(alias).collect()
                }
            };
            bindings.extend(found.into_iter().map(|record| ((file_at, site_at), record)));
        }
    }
    bindings
}

/// What the script analysis proves about a site: its evidence and its facts.
type Proven<'p> = (Option<&'p Vec<String>>, Option<&'p Vec<String>>);

/// `reference["evidence_ids"] = script_evidence.get(...)` and `["fact_ids"] = script_fact_ids...`,
/// and then the alias bindings that the proven site gives.
fn prove<D>(
    kept: &Kept,
    place: &Place,
    site: &Site,
    record: &mut Record<D>,
    proven: Option<Proven<'_>>,
) -> Vec<Record<BindingFact>> {
    let Some((evidence, facts)) = proven else {
        return Vec::new();
    };
    if let Some(ids) = evidence {
        record.evidence_ids = ids.iter().map(EvidenceId::new).collect();
    }
    let ids = facts.cloned().unwrap_or_default();
    record.fact_ids = ids.iter().map(FactId::new).collect();
    let evidence_ids: Vec<String> = record
        .evidence_ids
        .iter()
        .map(|id| id.as_str().to_owned())
        .collect();
    alias_bindings(kept, place, site, &evidence_ids, facts)
}

/// The key of a site in the maps of the script analysis.
fn site_key(kept: &Kept, site: &Site) -> SiteKey {
    let path = site
        .path
        .map(|at| kept.sites.paths.names(at, kept.text.as_bytes()));
    SiteKey::new(site.kind, &site.span, &path.unwrap_or_default())
}

/// `_script_alias_bindings`: the binding that an alias gets from the use that initializes it.
fn alias_bindings(
    kept: &Kept,
    place: &Place,
    site: &Site,
    made: &[String],
    facts: Option<&Vec<String>>,
) -> Vec<Record<BindingFact>> {
    let Some((first, rest)) = facts.and_then(|facts| facts.split_first()) else {
        return Vec::new();
    };
    let aliases = kept.script.script.aliases.iter();
    aliases
        .filter(|alias| alias.reference_span == site.span)
        .map(|alias| {
            let proof = (made.to_vec(), rest.to_vec());
            binding_record(place, first, &alias.name, proof)
        })
        .collect()
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

/// The reason and the id of the definition (`if reason:`).
fn reason(resolved: &Resolved) -> Option<String> {
    resolved
        .reason
        .filter(|reason| !reason.is_empty())
        .map(str::to_owned)
}

fn source_definition(place: &Place) -> Nullable<FactId> {
    place
        .source_id
        .as_ref()
        .map_or(Nullable::Absent, |id| Nullable::Value(FactId::new(id)))
}

fn subjects(place: &Place, resolved: &Resolved) -> Vec<String> {
    let mut found = vec![place.scope.clone()];
    found.extend(resolved.candidates.iter().cloned());
    found.retain(|value| !value.is_empty());
    found.sort();
    found
}

/// The record of a site: the same fields for a call and a reference.
fn site_record<D>(id: String, title: String, parts: (Vec<String>, String), data: D) -> Record<D> {
    let (subjects, evidence) = parts;
    Record {
        id: FactId::new(id),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title,
        subjects,
        evidence_ids: vec![EvidenceId::new(evidence)],
        fact_ids: Vec::new(),
        data,
    }
}

/// `_reference_record`.
fn reference(
    kept: &Kept,
    place: &Place,
    site: &Site,
    resolved: &Resolved,
    evidence: String,
) -> Record<ReferenceFact> {
    let expression = expression(kept, site);
    let usage = match site.usage {
        SiteUse::Type => Use::Type,
        SiteUse::Value => Use::Value,
        SiteUse::Member => Use::Member,
    };
    let mut data = ReferenceData::new(
        expression.clone(),
        (ModuleName::new(place.module), place.scope.clone()),
        (resolved.status, usage),
        resolved.candidates.clone(),
    );
    data.reason = reason(resolved);
    data.source_definition_id = source_definition(place);
    let id = stable_id(
        "TSREF",
        &[
            Part::Text(place.module),
            Part::Number(site.span.line),
            Part::Number(site.span.column),
            Part::Text(&expression),
        ],
    );
    let parts = (subjects(place, resolved), evidence);
    site_record(id, expression, parts, ReferenceFact::References(data))
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
) -> (Record<CallFact>, Vec<Record<BindingFact>>) {
    let expression = expression(kept, site);
    let id = stable_id(
        "TSCALL",
        &[
            Part::Text(place.module),
            Part::Number(site.span.line),
            Part::Number(site.span.column),
            Part::Text(&expression),
        ],
    );
    let mut data = CallData::new(
        expression.clone(),
        (ModuleName::new(place.module), place.scope.clone()),
        resolved.status,
        resolved.candidates.clone(),
    );
    data.reason = reason(resolved);
    data.source_definition_id = source_definition(place);
    let mut bindings = Vec::new();
    if site.kind == SiteKind::New {
        data.construction = Nullable::Value(construction(table, resolved));
        let values = result_binding(cited, kept, place, site, &id);
        bindings = values
            .iter()
            .map(|value| {
                let evidence = value.evidence_ids.iter().map(|id| id.as_str().to_owned());
                let proof = (evidence.collect(), Vec::new());
                binding_record(place, value.id.as_str(), &value.name, proof)
            })
            .collect();
        data.result_bindings = Some(values);
    }
    let parts = (subjects(place, resolved), evidence);
    let record = site_record(id, expression, parts, CallFact::Calls(data));
    (record, bindings)
}

/// The `construction` of a `new` expression: the targets that are classes.
fn construction(table: &SymbolTable, resolved: &Resolved) -> Construction {
    let targets: Vec<String> = resolved
        .candidates
        .iter()
        .filter(|target| table.class_count(target) > 0)
        .cloned()
        .collect();
    let status = if targets.len() == 1 && resolved.status == Status::Resolved {
        Status::Resolved
    } else if targets.is_empty() {
        Status::Unresolved
    } else {
        Status::PartiallyResolved
    };
    let reason = if status == Status::Resolved {
        "Unique local classifier construction"
    } else {
        resolved
            .reason
            .filter(|reason| !reason.is_empty())
            .unwrap_or("Construction target is not proven")
    };
    Construction {
        candidates_truncated: false,
        reason: reason.to_owned(),
        status,
        targets,
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
        annotation: site.assignment_annotation.clone(),
        definition_contexts: Vec::new(),
        evidence_ids: vec![EvidenceId::new(evidence)],
        id: FactId::new(id),
        initializer: initializer.decode(data),
        name,
        target_kind: "name".to_owned(),
    }]
}

/// `_binding_records` for one value: the id, the name, the evidence and the proving facts.
fn binding_record(
    place: &Place,
    id: &str,
    name: &str,
    proof: (Vec<String>, Vec<String>),
) -> Record<BindingFact> {
    let data = BindingData {
        binding: Some(name.to_owned()),
        source_scope: place.scope.clone(),
        ..BindingData::in_module(place.module)
    };
    let (mut evidence_ids, fact_ids) = proof;
    evidence_ids.sort();
    Record {
        id: FactId::new(id),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: format!("{}.{name} binding", place.scope),
        subjects: vec![place.scope.clone()],
        evidence_ids: evidence_ids.into_iter().map(EvidenceId::new).collect(),
        fact_ids: fact_ids.into_iter().map(FactId::new).collect(),
        data: BindingFact::Bindings(data),
    }
}

#[cfg(test)]
#[path = "site_records_tests.rs"]
mod tests;
