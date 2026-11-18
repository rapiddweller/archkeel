// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `call_owner` selects lexical callers and matches an exact target (AD-904).

use archkeel_contract::{CallOwner, RuleKind};
use archkeel_store::{CallOwners, OwnedCall};

use crate::causes::Cause;
use crate::ownership::in_scope;
use crate::{Graph, Model, Reason, Unsupported};

/// One proved call outside a rule's permitted source scopes.
pub struct ForbiddenCall<'a> {
    /// The call fact id.
    pub fact_id: &'a str,
    /// The lexical source of the call.
    pub source: &'a str,
    /// The qualified target of the call.
    pub target: &'a str,
    /// The source evidence for the proved call.
    pub evidence: &'a [String],
}

/// The exact calls that break the rule, even if other call sites are undecided.
pub fn call_owner_violations<'a>(
    model: &'a Model,
    rule: &CallOwner,
) -> Result<Vec<ForbiddenCall<'a>>, Reason> {
    let calls = CallOwners::calls(live(model, rule)?);
    let found = calls.iter().filter(|call| {
        model.selects(&call.module)
            && in_scope(&call.scope, rule.source().as_text())
            && call.target == rule.target().as_text()
            && !allowed(rule, &call.module, &call.scope)
    });
    Ok(found.map(violation).collect())
}

fn violation(call: &OwnedCall) -> ForbiddenCall<'_> {
    ForbiddenCall {
        fact_id: call.site.as_str(),
        source: &call.scope,
        target: &call.target,
        evidence: &call.evidence,
    }
}

fn live<'a>(model: &'a Model, rule: &CallOwner) -> Result<&'a CallOwners, Reason> {
    let live = Graph::call_owners(model.graph()).ok_or(Cause::Receipt(
        "call ownership needs a live Python call inventory; saved evidence is not replayable",
    ))?;
    if !CallOwners::protects(live, rule.target().as_text()) {
        return Err(Reason::Unsupported(Unsupported::Rule(RuleKind::CallOwner)));
    }
    Ok(live)
}

fn allowed(rule: &CallOwner, module: &str, scope: &str) -> bool {
    rule.allowed_sources()
        .iter()
        .any(|allow| in_scope(scope, allow.as_text()))
        || rule
            .exact_sources()
            .iter()
            .any(|allow| allow.as_text() == module || allow.as_text() == scope)
}

pub(crate) fn receipt(model: &Model, rule: &CallOwner) -> Result<(), Reason> {
    let live = live(model, rule)?;
    let calls = CallOwners::calls(live);
    let source = rule.source().as_text();
    let mut selected = calls
        .iter()
        .any(|call| model.selects(&call.module) && in_scope(&call.scope, source));
    for (_, module) in Graph::modules(model.graph()).iter() {
        let name = module.name();
        if !model.selects(name) {
            continue;
        }
        selected |= in_scope(name, source) && !module.blank();
        if (in_scope(name, source) || in_scope(source, name))
            && !allowed(rule, name, name)
            && !CallOwners::complete(live, name)
        {
            return Err(
                Cause::Receipt("call ownership: a selected call has no exact target").into(),
            );
        }
    }
    if !selected {
        return Err(Reason::NoSubjects);
    }
    Ok(())
}
