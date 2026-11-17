// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The completeness of a closed scope without an unlisted element (AD-747).
//!
//! A closed scope says that its owner holds no element of the listed kinds that the target does
//! not list. The core finds each unlisted element that the facts hold (`uml_scope_symbols.rs`).
//! When it finds none, the scope passes only if the facts also show that no other element can
//! exist: for each listed kind, the collector states the member inventory of the owner as
//! complete, and each member of that inventory is an entity of the owner in the table. The core
//! names no language here: the collector decides when an inventory is complete, and it writes
//! the reason when it is not.

use crate::symbols::Symbols;
use archkeel_contract::{EntityKind, TargetScope};

/// The prefix of each cause that keeps a closed scope without an unlisted element UNKNOWN.
const CAUSE: &str = "closed scope completeness";

fn cause(detail: &str) -> String {
    format!("{CAUSE}: {detail}")
}

/// The owner of a closed scope that a member inventory can prove, or the cause that none can.
/// `owner` is `None` for a module, package or component scope: no fact states a complete
/// inventory of a module. No fact states a complete site inventory either.
pub(crate) fn kinds<'o>(owner: Option<&'o str>, item: &TargetScope) -> Result<&'o str, String> {
    let Some(owner) = owner else {
        return Err(cause("the facts state no complete module inventory"));
    };
    if !item.relationship_kinds().is_empty() {
        return Err(cause("the facts state no complete site inventory"));
    }
    if item.entity_kinds().is_empty() {
        return Err(cause("the scope lists no member kind"));
    }
    Ok(owner)
}

/// `Ok` when the symbol `owner` of the table can hold no element of the entity kinds `kinds` that
/// the table does not show; else the cause that keeps its closed scope UNKNOWN.
pub(crate) fn proven(table: &Symbols, owner: &str, kinds: &[EntityKind]) -> Result<(), String> {
    let Some(inventories) = table.inventories.get(owner) else {
        return Err(cause(
            "the collector states no member inventory of the owner",
        ));
    };
    for kind in kinds {
        let mut found = inventories
            .iter()
            .filter(|inventory| inventory.kinds.contains(kind));
        let inventory = match (found.next(), found.next()) {
            (Some(inventory), None) => inventory,
            (None, _) => {
                let word = crate::uml_facts::word(kind);
                return Err(cause(&format!("no member inventory holds a {word}")));
            }
            (Some(_), Some(_)) => {
                return Err(cause(
                    "the owner has more than one member inventory of a kind",
                ));
            }
        };
        if !inventory.complete {
            let reason = inventory.reason.as_deref().unwrap_or("no reason stated");
            return Err(cause(&format!("the member inventory is partial: {reason}")));
        }
        let held = inventory.members.iter().all(|id| {
            table
                .get(id)
                .is_some_and(|member| member.parent.as_deref() == Some(owner))
        });
        if !held {
            return Err(cause("a member of the inventory is no entity of the owner"));
        }
    }
    Ok(())
}

#[cfg(test)]
#[path = "uml_inventory_tests.rs"]
mod tests;
