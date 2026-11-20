// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Admission of linked constructor and method witnesses (AD-1027).

use std::collections::{HashMap, HashSet};

use archkeel_facts::data::{CallableData, ClassData};
use archkeel_facts::envelope::{ConstructedCall, Evidence, Facts};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName};
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::{ClassKind, MethodKind, Status};
use archkeel_facts::{CallFact, Record, Section, SymbolFact};

/// One validated call whose invoked method is a direct member of the constructed class.
pub struct OwnedCall {
    /// The call fact.
    pub site: FactId,
    /// The source module of the call.
    pub module: String,
    /// The qualified source scope of the call.
    pub scope: String,
    /// The exact qualified method that the call invokes.
    pub target: String,
    /// The evidence of the call, allocation and declaration.
    pub evidence: Vec<EvidenceId>,
}

/// The live bound calls and the modules in which every written call has a witness.
pub struct CallOwners {
    calls: Vec<OwnedCall>,
    targets: HashSet<String>,
}

impl CallOwners {
    /// The validated method calls in producer order.
    pub fn calls(&self) -> &[OwnedCall] {
        &self.calls
    }

    /// The exact method declarations from the linked producer.
    pub fn targets(&self) -> &HashSet<String> {
        &self.targets
    }
}

const INVALID: &str = "invalid live constructor-to-method witness";

pub(crate) fn validate(facts: &Facts) -> Result<Option<CallOwners>, String> {
    let Some(witnesses) = &facts.constructed_calls else {
        return Ok(None);
    };
    if !facts.coverage.full_scope || facts.profile_limits.is_none() {
        return Err(INVALID.to_owned());
    }
    if Vec::is_empty(&witnesses.targets) && Vec::is_empty(&witnesses.calls) {
        return Ok(None);
    }
    let index = Index::of(facts);
    let mut targets = HashSet::new();
    let mut methods = HashSet::new();
    for id in &witnesses.targets {
        let (_, _, member, _) = index.target(id).ok_or(INVALID)?;
        if !methods.insert(id) || !targets.insert(member.qualified_name.clone()) {
            return Err(INVALID.to_owned());
        }
    }
    let mut calls = Vec::with_capacity(Vec::len(&witnesses.calls));
    let mut seen: HashSet<&FactId> = facts
        .direct_calls
        .iter()
        .flatten()
        .map(|(site, ..)| site)
        .collect();
    let mut counts = HashMap::<String, u64>::new();
    for witness in &witnesses.calls {
        if !methods.contains(&witness.method)
            || !seen.insert(&witness.call)
            || !seen.insert(&witness.constructor)
        {
            return Err(INVALID.to_owned());
        }
        let call = index.witness(witness).ok_or(INVALID)?;
        *counts.entry(call.module.clone()).or_default() += 2;
        calls.push(call);
    }
    let mut measured = HashSet::new();
    for row in facts.coverage.measures.iter().flatten() {
        if index.files.get(ModuleName::as_str(&row.module)) != Some(&String::as_str(&row.file))
            || !measured.insert(ModuleName::as_str(&row.module))
            || counts
                .get(ModuleName::as_str(&row.module))
                .copied()
                .unwrap_or(0)
                > row.calls_total
        {
            return Err(INVALID.to_owned());
        }
    }
    Ok(Some(CallOwners { calls, targets }))
}

struct Index<'a> {
    calls: HashMap<&'a FactId, &'a Record<CallFact>>,
    symbols: HashMap<&'a FactId, &'a Record<SymbolFact>>,
    imports: HashMap<&'a FactId, [&'a str; 4]>,
    evidence: HashMap<&'a EvidenceId, &'a Evidence>,
    files: HashMap<&'a str, &'a str>,
}

impl<'a> Index<'a> {
    fn of(facts: &'a Facts) -> Self {
        let mut index = Self {
            calls: HashMap::new(),
            symbols: HashMap::new(),
            imports: HashMap::new(),
            evidence: facts.evidence.iter().map(|item| (&item.id, item)).collect(),
            files: facts
                .files
                .iter()
                .map(|file| {
                    (
                        ModuleName::as_str(&file.module),
                        String::as_str(&file.rel_path),
                    )
                })
                .collect(),
        };
        for section in &facts.sections {
            match section {
                Section::Calls(rows) => index.calls.extend(rows.iter().map(|r| (&r.id, r))),
                Section::Symbols(rows) => index.symbols.extend(rows.iter().map(|r| (&r.id, r))),
                Section::Imports(rows) => index.imports.extend(rows.iter().filter_map(|record| {
                    let archkeel_facts::ImportFact::Import(data) = &record.data else {
                        return None;
                    };
                    archkeel_facts::data::ImportData::direct_symbol_route(data)
                        .map(|path| (&record.id, path))
                })),
                _ => {}
            }
        }
        index
    }

    fn witness(&self, witness: &ConstructedCall) -> Option<OwnedCall> {
        let call = *self.calls.get(&witness.call)?;
        let ctor = *self.calls.get(&witness.constructor)?;
        let (method, class, member, owner) = self.target(&witness.method)?;
        let (CallFact::Calls(outer), CallFact::Calls(inner)) = (&call.data, &ctor.data) else {
            return None;
        };
        let Nullable::Value(caller_id) = &outer.source_definition_id else {
            return None;
        };
        let (SymbolFact::Function(caller) | SymbolFact::Method(caller)) =
            &self.symbols.get(caller_id)?.data
        else {
            return None;
        };
        let Nullable::Value(allocation) = &inner.construction else {
            return None;
        };
        let valid = outer.source_definition_id == inner.source_definition_id
            && outer.source_scope == caller.qualified_name
            && outer.source_scope == inner.source_scope
            && outer.source_module == caller.module
            && outer.source_module == inner.source_module
            && outer.status == Status::Unresolved
            && outer.candidate_count == 0
            && !outer.candidates_truncated
            && Vec::is_empty(&outer.targets)
            && inner.status == Status::Resolved
            && allocation.status == Status::Resolved
            && !inner.candidates_truncated
            && !allocation.candidates_truncated
            && inner.candidate_count == 1
            && matches!(Vec::as_slice(&inner.targets), [name] if name == &owner.qualified_name)
            && allocation.targets == inner.targets;
        if !valid || !self.receiver(call, ctor, witness, &member.name) {
            return None;
        }
        let source = ModuleName::as_str(&outer.source_module);
        let provider = ModuleName::as_str(&owner.module);
        let name = String::as_str(&owner.name);
        let spelling = String::as_str(&inner.expression);
        let origin = match &witness.import {
            None => source == provider && spelling == name,
            Some(id) => {
                source != provider
                    && self.imports.get(id) == Some(&[source, provider, name, spelling])
            }
        };
        if !origin {
            return None;
        }
        let evidence = [
            call.evidence_ids.as_slice(),
            ctor.evidence_ids.as_slice(),
            method.evidence_ids.as_slice(),
            class.evidence_ids.as_slice(),
        ]
        .into_iter()
        .flatten()
        .cloned()
        .collect();
        Some(OwnedCall {
            site: call.id.clone(),
            module: source.to_owned(),
            scope: outer.source_scope.clone(),
            target: member.qualified_name.clone(),
            evidence,
        })
    }

    fn target(
        &self,
        id: &FactId,
    ) -> Option<(
        &Record<SymbolFact>,
        &Record<SymbolFact>,
        &CallableData,
        &ClassData,
    )> {
        let method = *self.symbols.get(id)?;
        let SymbolFact::Method(member) = &method.data else {
            return None;
        };
        let class = *self.symbols.get(member.lexical_parent_id.as_ref()?)?;
        let SymbolFact::Class(owner) = &class.data else {
            return None;
        };
        (member.method_kind == Some(MethodKind::Instance)
            && Vec::is_empty(&member.decorators)
            && member.source_binding_unique == Some(true)
            && owner.class_kind == Some(ClassKind::Class)
            && owner.class_header_static
            && owner.source_binding_unique
            && owner.lexical_parent_id.is_none()
            && Vec::is_empty(&owner.base_declarations)
            && member.parent.as_deref() == Some(String::as_str(&owner.qualified_name))
            && member.module == owner.module
            && member.qualified_name == format!("{}.{}", owner.qualified_name, member.name)
            && owner.qualified_name
                == format!("{}.{}", ModuleName::as_str(&owner.module), owner.name))
        .then_some((method, class, member, owner))
    }

    fn receiver(
        &self,
        call: &Record<CallFact>,
        ctor: &Record<CallFact>,
        proof: &ConstructedCall,
        member: &str,
    ) -> bool {
        let (CallFact::Calls(outer_call), CallFact::Calls(inner_call)) = (&call.data, &ctor.data)
        else {
            return false;
        };
        let sites = || {
            Some((
                self.evidence.get(call.evidence_ids.first()?)?,
                self.evidence.get(ctor.evidence_ids.first()?)?,
            ))
        };
        let Some((outer, inner)) = sites() else {
            return false;
        };
        if outer.file != inner.file
            || self.files.get(inner_call.source_module.as_str()) != Some(&inner.file.as_str())
        {
            return false;
        }
        match &proof.binding {
            None => {
                outer.line <= inner.line
                    && inner.end_line <= outer.end_line
                    && outer_call.expression == format!("{}().{member}", inner_call.expression)
            }
            Some(id) => inner_call
                .result_bindings
                .iter()
                .flatten()
                .find(|binding| &binding.id == id)
                .filter(|binding| {
                    outer_call.expression == format!("{}.{member}", binding.name)
                        && binding.initializer == format!("{}()", inner_call.expression)
                })
                .and_then(|binding| self.evidence.get(binding.evidence_ids.first()?))
                .is_some_and(|stmt| {
                    stmt.file == inner.file
                        && stmt.line <= inner.line
                        && inner.end_line <= stmt.end_line
                        && (stmt.end_line, stmt.column) < (outer.line, outer.column)
                }),
        }
    }
}
