// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The UML target of a contract tree (AD-526).
//!
//! Reference engine: `declared_tree_graph` of `ir/target_graph.py` at release 4.0.1 joins the
//! target of the root and the target of each mount into one target, and `compare_graphs` judges
//! that one target against the facts of the run. The core does the same and adds two stops that
//! 4.0.1 does not have. The row is UNKNOWN, with the cause named, when two contracts draw one
//! element, in one form or in two, and when a defined module of a mount lies outside the source
//! domain of that mount. Both stops hold the row before any comparison, so they cannot hide a
//! FAIL that 4.0.1 would not give: they only keep a PASS and a FAIL from resting on a target
//! that 4.0.1 refuses or that leaves its mount.

use std::collections::BTreeSet;

use archkeel_contract::{merge_targets, Entity, EntityKind, PresenceKind, Target};

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
    if let Some(reason) = conflict(&declared.parts).or_else(|| outside(tree, &declared.parts)) {
        return UmlOutcome::Unknown(UmlGap::Nested(reason));
    }
    let targets: Vec<&Target> = declared.parts.iter().map(|part| &part.target).collect();
    match merge_targets(&targets) {
        Some(merged) => crate::uml::compare(tree.root(), &merged, id),
        None => UmlOutcome::Unknown(UmlGap::NothingCompared),
    }
}
