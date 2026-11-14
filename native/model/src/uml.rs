// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The comparison of a UML target with the module and import facts (AD-494).
//!
//! Reference engine: `check/uml_compare.py` `compare_graphs` at release 4.0.1. The core makes the
//! assessments that module and import facts decide, with the same status as 4.0.1 or a stricter
//! one, and names each other assessment as undecided:
//!
//! - a defined module entity: PASS when one module of the reply has its name and its language;
//!   absent or ambiguous is UNKNOWN (4.0.1 never proves a module inventory complete);
//! - an `imports` relationship between two module entities: PASS when the reply has the edge,
//!   FAIL when it has not and the scope of the run is complete, else UNKNOWN;
//! - an open scope: PASS when its entity names one module or package of the reply;
//! - a closed scope over modules and imports: FAIL for each unlisted module or resolved import
//!   edge in it, else UNKNOWN (4.0.1 proves no module inventory complete);
//! - each other entity, relationship or scope kind: UNKNOWN, by its kind.
//!
//! A row is FAIL with any FAIL assessment, UNKNOWN with any other UNKNOWN assessment, and PASS
//! only with every assessment PASS and the scope proof of the run (`Scope::uml_complete`).

use std::collections::BTreeSet;

use archkeel_contract::{Entity, EntityKind, PresenceKind, Relationship, RelationshipKind, Target};

use crate::model::Model;
use crate::reason::UmlGap;
pub use crate::uml_facts::UmlDiff;
use crate::uml_facts::{entity, plain, word, Assessed, Facts};
use crate::verdict::Decision;

/// The input of the target row from the contract tree (AD-470, AD-494).
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum UmlTarget {
    /// The root target, which the core compares with the model of the root.
    Compare(Box<Target>),
    /// A cause that keeps the row UNKNOWN without a comparison.
    Gap(UmlGap),
}

/// The typed result of the target row.
#[derive(Clone, Debug)]
pub enum UmlOutcome {
    Pass(Decision),
    Fail(Vec<UmlDiff>),
    Unknown(UmlGap),
}

/// Compare the root target with the model of the root of the run; `id` is the row id.
pub fn compare(model: &Model, target: &Target, id: &str) -> UmlOutcome {
    let modules: Vec<&str> = target
        .entities()
        .iter()
        .filter(|item| *item.kind() == EntityKind::Module)
        .map(|item| item.qualified_name().as_str())
        .collect();
    let facts = Facts::of(model, &modules);
    let mut found: Vec<Assessed> = Vec::new();
    for entity in target.entities() {
        found.extend(entity_assessment(&facts, target, entity));
    }
    for edge in target.relationships() {
        if *edge.kind() != RelationshipKind::Requires {
            found.push(relationship(&facts, target, edge));
        }
    }
    for scope in target.scopes() {
        found.extend(crate::uml_scope::scope(&facts, target, scope));
    }
    verdict(&facts, found, id)
}

fn verdict(facts: &Facts<'_>, found: Vec<Assessed>, id: &str) -> UmlOutcome {
    if found.is_empty() {
        return UmlOutcome::Unknown(UmlGap::NothingCompared);
    }
    let mut diffs = Vec::new();
    let mut kinds = BTreeSet::new();
    let mut undecided = 0;
    for item in found {
        match item {
            Assessed::Pass => {}
            Assessed::Fail(diff) => diffs.push(diff),
            Assessed::Unknown(kind) => {
                undecided += 1;
                kinds.insert(kind);
            }
        }
    }
    if !diffs.is_empty() {
        return UmlOutcome::Fail(diffs);
    }
    if undecided > 0 {
        let kinds = kinds.into_iter().collect();
        return UmlOutcome::Unknown(UmlGap::Undecided {
            count: undecided,
            kinds,
        });
    }
    match crate::scope::uml_pass(facts.model, id, facts.read) {
        Ok(decision) => UmlOutcome::Pass(decision),
        Err(reason) => UmlOutcome::Unknown(UmlGap::Incomplete(reason.to_string())),
    }
}

fn entity_assessment(facts: &Facts<'_>, target: &Target, item: &Entity) -> Vec<Assessed> {
    if *item.kind() == EntityKind::Component {
        return Vec::new();
    }
    // `_entity`: a referenced endpoint without metadata has no assessment.
    if *item.presence() == PresenceKind::Referenced && plain(item) {
        return Vec::new();
    }
    if *item.kind() != EntityKind::Module {
        return vec![Assessed::Unknown(format!("{} entity", word(item.kind())))];
    }
    let found = facts.modules(item.qualified_name(), item.language());
    if found.len() != 1 {
        return vec![Assessed::Unknown(
            "module entity without one module".to_owned(),
        )];
    }
    let mut result = vec![Assessed::Pass];
    // `_containment`: a parent that is not a component is a lexical parent the core does not map.
    let parent = item
        .parent_id()
        .as_ref()
        .and_then(|id| entity(target, id.as_text()));
    if parent.is_some_and(|parent| *parent.kind() != EntityKind::Component) {
        result.push(Assessed::Unknown("module containment".to_owned()));
    }
    if !plain(item) {
        result.push(Assessed::Unknown("module detail".to_owned()));
    }
    result
}

fn relationship(facts: &Facts<'_>, target: &Target, edge: &Relationship) -> Assessed {
    let kind = word(edge.kind());
    if *edge.kind() != RelationshipKind::Imports {
        return Assessed::Unknown(format!("{kind} relationship"));
    }
    let ends = (
        entity(target, edge.source_id().as_text()),
        edge.target_id()
            .as_ref()
            .and_then(|id| entity(target, id.as_text())),
    );
    let (Some(source), Some(end)) = ends else {
        return Assessed::Unknown("imports relationship endpoint".to_owned());
    };
    // `_matches` reads a module fact only for a module entity; another kind needs symbol facts.
    if *source.kind() != EntityKind::Module || *end.kind() != EntityKind::Module {
        return Assessed::Unknown("imports relationship endpoint that is not a module".to_owned());
    }
    let modules = (
        facts.modules(source.qualified_name(), source.language()),
        facts.modules(end.qualified_name(), end.language()),
    );
    let ([from], [to]) = (modules.0.as_slice(), modules.1.as_slice()) else {
        return Assessed::Unknown("imports relationship endpoint".to_owned());
    };
    if facts.has_edge(from.name(), to.name()) {
        return Assessed::Pass;
    }
    // `_relationship`: a missing edge is FAIL only in a complete inventory.
    if !crate::scope::uml_run(facts.model, facts.read) {
        return Assessed::Unknown("imports relationship coverage".to_owned());
    }
    Assessed::Fail(UmlDiff {
        subject: edge.id().as_text().to_owned(),
        fact: format!("{} -> {}", from.name(), to.name()),
        cause: "declared import is absent",
        evidence: vec![from.evidence().to_owned()],
    })
}
