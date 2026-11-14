// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The scope assessments of a UML target (`_scope_assessments` and
//! `_closed_relationship_assessments` of `check/uml_compare.py`, AD-490).

use archkeel_contract::{CompletenessMode, EntityKind, RelationshipKind, Target, TargetScope};

use crate::uml::{entity, word, Assessed, Facts, UmlDiff};

/// The assessments of one scope.
pub(crate) fn scope(facts: &Facts<'_>, target: &Target, item: &TargetScope) -> Vec<Assessed> {
    let Some(owner) = entity(target, item.scope_id().as_text()) else {
        return vec![Assessed::Unknown("scope entity".to_owned())];
    };
    let name = owner.qualified_name();
    let module = match owner.kind() {
        EntityKind::Module => true,
        EntityKind::Component | EntityKind::Package => false,
        other => {
            return vec![Assessed::Unknown(format!(
                "scope of a {} entity",
                word(other)
            ))]
        }
    };
    if found(facts, name, owner.language(), module) != 1 {
        return vec![Assessed::Unknown(
            "scope without one module or package".to_owned(),
        )];
    }
    if *item.mode() == CompletenessMode::Open {
        return vec![Assessed::Pass];
    }
    let kinds_known = item
        .entity_kinds()
        .iter()
        .all(|kind| *kind == EntityKind::Module)
        && item
            .relationship_kinds()
            .iter()
            .all(|kind| *kind == RelationshipKind::Imports);
    if !kinds_known {
        return vec![Assessed::Unknown("closed scope of other kinds".to_owned())];
    }
    let mut extras = Vec::new();
    if item.entity_kinds().contains(&EntityKind::Module) {
        extras.extend(extra_modules(
            facts,
            target,
            owner.id().as_text(),
            name,
            module,
        ));
    }
    if item
        .relationship_kinds()
        .contains(&RelationshipKind::Imports)
    {
        extras.extend(extra_edges(
            facts,
            target,
            owner.id().as_text(),
            name,
            module,
        ));
    }
    if extras.is_empty() {
        // 4.0.1 proves no complete module inventory for a closed scope.
        return vec![Assessed::Unknown("closed scope completeness".to_owned())];
    }
    extras.into_iter().map(Assessed::Fail).collect()
}

/// The number of modules (for a module scope) or packages, else modules, named `name`.
fn found(facts: &Facts<'_>, name: &str, language: &str, module: bool) -> usize {
    let modules = facts.modules(name, language).len();
    if module || language != facts.language {
        return modules;
    }
    let packages = facts.model.graph().packages();
    let named = packages
        .iter()
        .filter(|(_, package)| package.name() == name)
        .count();
    if named > 0 {
        named
    } else {
        modules
    }
}

/// `_within`: a module scope holds its own module; a package or component scope holds the
/// modules below its name.
fn within(scope: &str, module_scope: bool, name: &str) -> bool {
    if module_scope {
        name == scope
    } else {
        name.strip_prefix(scope)
            .is_some_and(|rest| rest.starts_with('.'))
    }
}

/// The modules in the scope that the target does not list as module entities.
fn extra_modules(
    facts: &Facts<'_>,
    target: &Target,
    subject: &str,
    scope: &str,
    module_scope: bool,
) -> Vec<UmlDiff> {
    let listed = |name: &str| {
        target
            .entities()
            .iter()
            .any(|item| *item.kind() == EntityKind::Module && item.qualified_name() == name)
    };
    let modules = facts.model.graph().modules();
    modules
        .iter()
        .map(|(_, module)| module)
        .filter(|module| module.name() != scope || !module_scope)
        .filter(|module| within(scope, module_scope, module.name()) && !listed(module.name()))
        .map(|module| UmlDiff {
            subject: subject.to_owned(),
            fact: module.name().to_owned(),
            cause: "closed scope holds an unlisted module",
            evidence: vec![module.evidence().to_owned()],
        })
        .collect()
}

/// The resolved import edges from the scope that no `imports` relationship of the target lists.
fn extra_edges(
    facts: &Facts<'_>,
    target: &Target,
    subject: &str,
    scope: &str,
    module_scope: bool,
) -> Vec<UmlDiff> {
    let name_of = |id: &str| entity(target, id).map(|item| item.qualified_name().to_owned());
    let listed: Vec<(String, String)> = target
        .relationships()
        .iter()
        .filter(|edge| *edge.kind() == RelationshipKind::Imports)
        .filter_map(|edge| {
            let end = edge.target_id().as_ref()?;
            Some((
                name_of(edge.source_id().as_text())?,
                name_of(end.as_text())?,
            ))
        })
        .collect();
    facts
        .model
        .graph()
        .imports()
        .iter()
        .filter(|import| import.resolved == crate::imports::Resolved::Local)
        .filter(|import| within(scope, module_scope, &import.source_module))
        .filter(|import| {
            !listed
                .iter()
                .any(|(from, to)| *from == import.source_module && *to == import.target_module)
        })
        .map(|import| UmlDiff {
            subject: subject.to_owned(),
            fact: format!("{} -> {}", import.source_module, import.target_module),
            cause: "closed scope holds an unlisted import",
            evidence: import.evidence.clone(),
        })
        .collect()
}
