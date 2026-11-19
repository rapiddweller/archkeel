// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The source records of an Explorer scan, with their original identities and evidence.

use std::collections::HashMap;

use archkeel_facts::envelope::{Facts, Target};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::{EvidenceClass, Status};
use archkeel_facts::{CallFact, FactData, ImportFact, Record, Section};
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
    module: Option<String>,
    qualified_name: Option<String>,
    evidence_ids: Vec<EvidenceId>,
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

fn call(row: &Record<CallFact>, target: Option<&FactId>) -> Call {
    let (CallFact::Calls(d)
    | CallFact::Call(d)
    | CallFact::ResolvedCall(d)
    | CallFact::PartiallyResolvedCall(d)
    | CallFact::UnresolvedCall(d)) = &row.data;
    Call {
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
    }
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
    reply
        .filter(|_| enabled)
        .map(|r| project(&r.reply().facts, r.analysis_capabilities().language))
        .into_iter()
        .collect()
}

fn project(facts: &Facts, language: &'static str) -> ExplorerPart {
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
        imports: None,
    };
    let targets: HashMap<_, _> = facts.imports.iter().map(|t| (t.import_id(), t)).collect();
    let direct: HashMap<_, _> = facts
        .direct_calls
        .iter()
        .flatten()
        .map(|(site, declaration, _, _)| (site, declaration))
        .collect();
    for section in &facts.sections {
        match section {
            Section::Symbols(rows) => {
                part.symbols = Some(
                    rows.iter()
                        .map(|row| {
                            let fields = row.data.fields();
                            Symbol {
                                id: row.id.clone(),
                                kind: FactData::wire_kind(&row.data).to_owned(),
                                evidence_class: EvidenceClass::as_str(row.evidence_class),
                                module: fields.module.flatten().map(str::to_owned),
                                qualified_name: fields.qualified_name.map(str::to_owned),
                                evidence_ids: row.evidence_ids.clone(),
                            }
                        })
                        .collect(),
                )
            }
            Section::Calls(rows) => {
                part.calls = Some(
                    rows.iter()
                        .map(|row| call(row, direct.get(&row.id).copied()))
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
