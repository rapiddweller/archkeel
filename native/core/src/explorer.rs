// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The source records of an Explorer scan, with their original identities and evidence.

use std::collections::HashMap;

use archkeel_facts::envelope::{SourceCallCandidate, Target};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::nested::MemberInventory;
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::{EvidenceClass, InventoryStatus, MemberKind, MethodKind, Status};
use archkeel_facts::{CallFact, FactData, ImportFact, Record, Section, SymbolFact};
use schemars::JsonSchema;
use serde::Serialize;

#[derive(Serialize, JsonSchema)]
pub(crate) struct ExplorerPart {
    part: Option<String>,
    language: &'static str,
    files: Vec<File>,
    symbols: Option<Vec<Symbol>>,
    calls: Option<Vec<Call>>,
    imports: Option<Vec<Import>>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    source_call_candidates: Vec<SourceCallCandidate>,
}

#[derive(Serialize, JsonSchema)]
struct File {
    module: String,
    path: String,
}

#[derive(Serialize, JsonSchema)]
struct Symbol {
    id: FactId,
    kind: String,
    evidence_class: &'static str,
    evidence_ids: Vec<EvidenceId>,
    module: Option<String>,
    qualified_name: Option<String>,
    lexical_parent_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    attributes: Option<Vec<Attribute>>,
    method_kind: Option<MethodKind>,
    accessor_kind: Option<String>,
    property_operation: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    property_names: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    member_inventories: Option<Vec<Inventory>>,
}

#[derive(Serialize, JsonSchema)]
struct Attribute {
    definition_id: FactId,
    name: String,
    annotation: Option<String>,
    #[serde(rename = "static", skip_serializing_if = "Option::is_none")]
    is_static: Option<bool>,
    evidence_ids: Vec<EvidenceId>,
}

#[derive(Serialize, JsonSchema)]
struct Inventory {
    definition_ids: Vec<FactId>,
    kind: MemberKind,
    reason: Option<String>,
    schema_version: String,
    status: InventoryStatus,
}

fn inventory(data: &MemberInventory) -> Inventory {
    Inventory {
        definition_ids: data.definition_ids.clone(),
        kind: data.kind,
        reason: data.reason.clone(),
        schema_version: data.schema_version.clone(),
        status: data.status,
    }
}

fn symbol(row: &Record<SymbolFact>) -> Symbol {
    let fields = FactData::fields(&row.data);
    let method = match &row.data {
        SymbolFact::Method(method) | SymbolFact::Function(method) => Some(method),
        _ => None,
    };
    let class = match &row.data {
        SymbolFact::Class(class) => Some(class),
        _ => None,
    };
    Symbol {
        id: row.id.clone(),
        kind: FactData::wire_kind(&row.data).to_owned(),
        evidence_class: EvidenceClass::as_str(row.evidence_class),
        module: fields.module.flatten().map(str::to_owned),
        qualified_name: fields.qualified_name.map(str::to_owned),
        lexical_parent_id: fields.lexical_parent_id.map(str::to_owned),
        method_kind: method.and_then(|m| m.method_kind),
        accessor_kind: method.and_then(|m| m.accessor_kind.clone()),
        property_operation: method
            .and_then(|m| m.property_binding.as_ref())
            .map(|p| p.operation.clone()),
        property_names: class.and_then(|c| c.property_members.clone()),
        attributes: class.map(|c| {
            c.attribute_declarations
                .iter()
                .map(|attr| Attribute {
                    definition_id: attr.definition_id.clone(),
                    name: attr.name.clone(),
                    annotation: attr.annotation.clone(),
                    is_static: attr.is_static,
                    evidence_ids: attr.evidence_ids.clone(),
                })
                .collect()
        }),
        member_inventories: class.map(|c| c.member_inventories.iter().map(inventory).collect()),
        evidence_ids: row.evidence_ids.clone(),
    }
}

#[derive(Serialize, JsonSchema)]
struct Call {
    id: FactId,
    kind: String,
    evidence_class: &'static str,
    source_module: String,
    source_scope: String,
    source_definition_id: Option<FactId>,
    target_definition_id: Option<FactId>,
    expression: String,
    targets: Vec<String>,
    status: &'static str,
    reason: Option<String>,
    candidates_truncated: bool,
    candidate_count: i64,
    evidence_ids: Vec<EvidenceId>,
}

#[derive(Serialize, JsonSchema)]
struct Import {
    id: FactId,
    kind: String,
    evidence_class: &'static str,
    source_module: String,
    target_module: String,
    symbol: Option<String>,
    specifier: Option<String>,
    inferred_receiver: bool,
    resolution: &'static str,
    reason: Option<String>,
    evidence_ids: Vec<EvidenceId>,
}

type RustMethods<'a> = HashMap<(&'a EvidenceId, &'a str), Option<&'a FactId>>;

fn rust_methods(sections: &[Section]) -> RustMethods<'_> {
    let mut methods = HashMap::new();
    for section in sections {
        let Section::Symbols(rows) = section else {
            continue;
        };
        for row in rows {
            let SymbolFact::Method(method) = &row.data else {
                continue;
            };
            let [declaration] = row.evidence_ids.as_slice() else {
                continue;
            };
            methods
                .entry((declaration, String::as_str(&method.qualified_name)))
                .and_modify(|target| *target = None)
                .or_insert(Some(&row.id));
        }
    }
    methods
}

fn rust_method_target<'a>(row: &Record<CallFact>, methods: &RustMethods<'a>) -> Option<&'a FactId> {
    let CallFact::Calls(call) = &row.data else {
        return None;
    };
    let [name] = call.targets.as_slice() else {
        return None;
    };
    let [declaration] = call.target_evidence_ids.as_deref()? else {
        return None;
    };
    if call.status != Status::Resolved || call.candidates_truncated || call.candidate_count != 1 {
        return None;
    }
    methods
        .get(&(declaration, String::as_str(name)))
        .copied()
        .flatten()
}

fn call(
    row: &Record<CallFact>,
    target: Option<&FactId>,
    owner: Option<(&archkeel_store::OwnedCall, &FactId)>,
) -> Call {
    let (CallFact::Calls(d)
    | CallFact::Call(d)
    | CallFact::ResolvedCall(d)
    | CallFact::PartiallyResolvedCall(d)
    | CallFact::UnresolvedCall(d)) = &row.data;
    let mut projected = Call {
        id: row.id.clone(),
        kind: FactData::wire_kind(&row.data).to_owned(),
        evidence_class: EvidenceClass::as_str(row.evidence_class),
        source_module: ModuleName::as_str(&d.source_module).to_owned(),
        source_scope: d.source_scope.clone(),
        source_definition_id: match &d.source_definition_id {
            Nullable::Value(id) => Some(id.clone()),
            _ => None,
        },
        target_definition_id: target.cloned(),
        expression: d.expression.clone(),
        targets: d.targets.clone(),
        status: Status::as_str(d.status),
        reason: d.reason.clone(),
        candidates_truncated: d.candidates_truncated,
        candidate_count: d.candidate_count,
        evidence_ids: row.evidence_ids.clone(),
    };
    if let Some((owner, method)) = owner {
        projected.target_definition_id = Some(method.clone());
        projected.targets = vec![owner.target.clone()];
        projected.status = Status::as_str(Status::Resolved);
        projected.reason =
            Some("method of a fresh instance with a validated construction".to_owned());
        projected.candidate_count = 1;
    }
    projected
}

fn import(row: &Record<ImportFact>, target: Option<&Target>) -> Import {
    let d = ImportFact::data(&row.data);
    let (resolution, target, reason) = match target {
        Some(Target::Local { module, .. }) => ("local", ModuleName::as_str(module), None),
        Some(Target::External { package, .. }) => ("external", PackageName::as_str(package), None),
        Some(Target::Builtin { name, .. }) => ("builtin", String::as_str(name), None),
        Some(Target::Unresolved { reason, .. }) => (
            "unresolved",
            ModuleName::as_str(&d.target_module),
            Some(reason.clone()),
        ),
        None => ("unknown", ModuleName::as_str(&d.target_module), None),
    };
    Import {
        id: row.id.clone(),
        kind: FactData::wire_kind(&row.data).to_owned(),
        evidence_class: EvidenceClass::as_str(row.evidence_class),
        source_module: ModuleName::as_str(&d.source_module).to_owned(),
        target_module: target.to_owned(),
        symbol: d.symbol.clone(),
        specifier: d.specifier.clone(),
        inferred_receiver: d.inferred_receiver,
        resolution,
        reason,
        evidence_ids: row.evidence_ids.clone(),
    }
}

/// Project only collected sections. A missing section stays null even when another was read.
pub(crate) fn parts(reply: Option<&archkeel_store::Ingested>, enabled: bool) -> Vec<ExplorerPart> {
    reply.filter(|_| enabled).map(project).into_iter().collect()
}

fn project(reply: &archkeel_store::Ingested) -> ExplorerPart {
    let facts = &reply.reply().facts;
    let language = reply.analysis_capabilities().language;
    let mut part = ExplorerPart {
        part: None,
        language,
        files: facts
            .files
            .iter()
            .map(|f| File {
                module: ModuleName::as_str(&f.module).to_owned(),
                path: f.rel_path.clone(),
            })
            .collect(),
        symbols: None,
        calls: None,
        source_call_candidates: facts.source_call_candidates.clone(),
        imports: None,
    };
    let targets: HashMap<_, _> = facts.imports.iter().map(|t| (t.import_id(), t)).collect();
    let direct: HashMap<_, _> = facts
        .direct_calls
        .iter()
        .flatten()
        .map(|(site, declaration, _, _)| (site, declaration))
        .collect();
    let owners: &[archkeel_store::OwnedCall] = match reply.call_owners() {
        Some(owners) => {
            let owners: &archkeel_store::CallOwners = owners;
            owners.calls()
        }
        None => &[],
    };
    // The store validates every witness and returns the calls in producer order.
    let constructed: HashMap<_, _> = owners
        .iter()
        .zip(
            facts
                .constructed_calls
                .iter()
                .flat_map(|block| &block.calls),
        )
        .map(|(owner, witness)| (&owner.site, (owner, &witness.method)))
        .collect();
    let methods = if language == "rust" {
        rust_methods(&facts.sections)
    } else {
        HashMap::new()
    };
    for section in &facts.sections {
        match section {
            Section::Symbols(rows) => {
                part.symbols = Some(rows.iter().map(symbol).collect());
            }
            Section::Calls(rows) => {
                part.calls = Some(
                    rows.iter()
                        .map(|row| {
                            call(
                                row,
                                direct
                                    .get(&row.id)
                                    .copied()
                                    .or_else(|| rust_method_target(row, &methods)),
                                constructed.get(&row.id).copied(),
                            )
                        })
                        .collect(),
                )
            }
            Section::Imports(rows) => {
                part.imports = Some(
                    rows.iter()
                        .map(|row| import(row, targets.get(&row.id).copied()))
                        .collect(),
                )
            }
            _ => {}
        }
    }
    part
}
