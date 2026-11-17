// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The member inventories of a class as the model reads them (AD-747): the entity kinds of each
//! inventory, whether the collector states it complete, why not, and the ids of its members.

use archkeel_contract::EntityKind;
use archkeel_facts::nested::MemberInventory;
use archkeel_facts::vocab::{InventoryStatus, MemberKind};

/// One member inventory of a class.
#[derive(Clone, Debug)]
pub(crate) struct Inventory {
    /// The entity kinds of its members: an enum literal is an attribute declaration of its enum.
    pub(crate) kinds: &'static [EntityKind],
    pub(crate) complete: bool,
    /// Why the collector does not state it complete.
    pub(crate) reason: Option<String>,
    /// The ids of the members.
    pub(crate) members: Vec<String>,
}

impl Inventory {
    pub(crate) fn of(record: &MemberInventory) -> Self {
        let kinds: &'static [EntityKind] = match record.kind {
            MemberKind::Attribute => &[EntityKind::Attribute, EntityKind::EnumLiteral],
            MemberKind::Method => &[EntityKind::Method],
        };
        Inventory {
            kinds,
            complete: record.status == InventoryStatus::Complete,
            reason: record.reason.clone(),
            members: record
                .definition_ids
                .iter()
                .map(|id| id.as_str().to_owned())
                .collect(),
        }
    }
}
