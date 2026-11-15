// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The UML target of a contract tree (AD-526).
//!
//! Reference engine: `declared_tree_graph` of `ir/target_graph.py` at release 4.0.1 joins the
//! target of the root and the target of each mount into one target, and `compare_graphs` judges
//! that one target against the facts of the run. The core does the same and adds three stops. The
//! row is UNKNOWN, with the cause named, when two contracts draw one element (4.0.1 refuses it),
//! when a defined module of a mount lies outside the source domain of that mount, and when a
//! reference meets a definition of another contract and 4.0.1 refuses to link it. The stops hold
//! the row before any comparison, so they only keep a PASS or a FAIL from resting on a target
//! that 4.0.1 refuses or that leaves its mount.

use std::collections::BTreeSet;

use archkeel_contract::{bare_reference, merge_targets, Entity, EntityKind, PresenceKind, Target};

use crate::reason::UmlGap;
use crate::tree::ModelTree;
use crate::uml::UmlOutcome;
use crate::uml_declared::{UmlDeclared, UmlPart};

fn key(item: &Entity) -> (String, String) {
    (item.qualified_name().clone(), item.language().clone())
}

/// The element that a part defines: not a component and not a bare endpoint of a relationship.
fn defined(item: &Entity) -> bool {
    *item.kind() != EntityKind::Component && *item.presence() != PresenceKind::Referenced
}

/// The first element that two parts define. 4.0.1 refuses such a tree as a duplicate planned
/// entity, whether the parts draw it in one form or in two.
fn conflict(parts: &[UmlPart]) -> Option<String> {
    let mut seen: BTreeSet<(String, String)> = BTreeSet::new();
    for part in parts {
        let mine: BTreeSet<(String, String)> = part
            .target
            .entities()
            .iter()
            .filter(|item| defined(item))
            .map(key)
            .collect();
        if let Some(name) = mine.iter().find(|name| seen.contains(*name)) {
            return Some(format!(
                "the contracts of the tree both draw {}: 4.0.1 refuses a duplicate planned entity",
                name.0
            ));
        }
        seen.extend(mine);
    }
    None
}

/// The identity that `_link_references` of 4.0.1 matches: language, kind and qualified name.
fn same(left: &Entity, right: &Entity) -> bool {
    left.language() == right.language()
        && left.kind() == right.kind()
        && left.qualified_name() == right.qualified_name()
}

fn parent_of<'t>(target: &'t Target, item: &Entity) -> Option<&'t Entity> {
    let id = item.parent_id().as_ref()?;
    target.entities().iter().find(|found| found.id() == id)
}

/// True when 4.0.1 refuses to link `item` of the part `part` to `definition` of the part `home`:
/// it carries more than a bare reference, a scope names it, or its parent is not the parent of
/// the definition.
fn unlinkable(part: &Target, item: &Entity, (home, definition): (&Target, &Entity)) -> bool {
    let owned = part
        .scopes()
        .iter()
        .any(|scope| scope.scope_id() == item.id());
    let moved = item.parent_id().is_some()
        && !parent_of(part, item)
            .zip(parent_of(home, definition))
            .is_some_and(|(left, right)| same(left, right));
    !bare_reference(item) || owned || moved
}

/// The first referenced entity that meets a planned definition in another part and that 4.0.1
/// refuses to link (`_link_references` runs on the joined graph). The core links each contract
/// alone, so it must not give PASS for such a tree.
fn link(parts: &[UmlPart]) -> Option<String> {
    let references = parts.iter().enumerate().flat_map(|(at, part)| {
        let found = part.target.entities().iter();
        found
            .filter(|item| *item.presence() == PresenceKind::Referenced)
            .map(move |item| (at, item))
    });
    for (at, item) in references {
        let definitions = parts
            .iter()
            .enumerate()
            .filter(|(other, _)| *other != at)
            .flat_map(|(_, found)| found.target.entities().iter().map(|e| (&found.target, e)))
            .filter(|(_, e)| *e.presence() == PresenceKind::Planned && same(e, item));
        for definition in definitions {
            if unlinkable(&parts[at].target, item, definition) {
                return Some(format!(
                    "the contracts of the tree reference {} in a form that 4.0.1 refuses to link",
                    item.qualified_name()
                ));
            }
        }
    }
    None
}

/// The first module that a mount draws and the reply has, outside the source domain of the mount.
fn outside(tree: &ModelTree, parts: &[UmlPart]) -> Option<String> {
    let observed = tree.root().graph().observed();
    let modules = tree.root().graph().modules();
    for part in parts {
        let Some(model) = part.mount.and_then(|at| tree.mounts().get(at)) else {
            continue;
        };
        let stray = part.target.entities().iter().find(|item| {
            *item.kind() == EntityKind::Module
                && defined(item)
                && item.language() == observed.language
                && modules
                    .iter()
                    .any(|(_, module)| module.name() == item.qualified_name())
                && !model.selects(item.qualified_name())
        });
        if let Some(item) = stray {
            return Some(format!(
                "the target of an inside contract draws the module {} outside the mount",
                item.qualified_name()
            ));
        }
    }
    None
}

/// Compare the declared intent of the tree with the facts of the run; `id` is the row id.
pub fn compare_tree(tree: &ModelTree, declared: &UmlDeclared, id: &str) -> UmlOutcome {
    if let Some(reason) = conflict(&declared.parts)
        .or_else(|| link(&declared.parts))
        .or_else(|| outside(tree, &declared.parts))
    {
        return UmlOutcome::Unknown(UmlGap::Nested(reason));
    }
    let targets: Vec<&Target> = declared.parts.iter().map(|part| &part.target).collect();
    match merge_targets(&targets) {
        Some(merged) => crate::uml::compare(tree.root(), &merged, id),
        None => UmlOutcome::Unknown(UmlGap::NothingCompared),
    }
}
