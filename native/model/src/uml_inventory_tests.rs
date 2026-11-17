// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A closed scope of a class without an unlisted member passes only with a complete member
//! inventory of each listed kind, whose members the table holds in the class (AD-747).

use archkeel_contract::EntityKind;
use archkeel_facts::ids::FactId;
use archkeel_facts::nested::MemberInventory;
use archkeel_facts::vocab::{InventoryStatus, MemberKind};

use super::proven;
use crate::symbol_inventory::Inventory;
use crate::symbols::{Entity, Symbols};

fn inventory(kind: MemberKind, complete: bool, members: &[&str]) -> Inventory {
    Inventory::of(&MemberInventory {
        definition_ids: members.iter().map(|id| FactId::new(*id)).collect(),
        kind,
        reason: (!complete).then(|| "a member can be added elsewhere".to_owned()),
        schema_version: "1.0.0".to_owned(),
        status: if complete {
            InventoryStatus::Complete
        } else {
            InventoryStatus::Partial
        },
    })
}

/// The class `client` with the attribute `token` and the method `run`, and its inventories.
fn table(inventories: Vec<Inventory>) -> Symbols {
    let mut table = Symbols::default();
    let entity = |id: &str, kind: EntityKind, parent: Option<&str>| {
        let mut entity = Entity::named(id.to_owned(), kind, id, Vec::new());
        entity.parent = parent.map(str::to_owned);
        entity
    };
    table.push(entity("client", EntityKind::Class, None));
    table.push(entity("token", EntityKind::Attribute, Some("client")));
    table.push(entity("run", EntityKind::Method, Some("client")));
    table.push(entity("other", EntityKind::Method, None));
    table.inventories.insert("client".to_owned(), inventories);
    table
}

fn both(attributes: bool, methods: bool) -> Vec<Inventory> {
    vec![
        inventory(MemberKind::Attribute, attributes, &["token"]),
        inventory(MemberKind::Method, methods, &["run"]),
    ]
}

const MEMBERS: [EntityKind; 2] = [EntityKind::Attribute, EntityKind::Method];

#[test]
fn complete_inventories_of_each_listed_kind_prove_the_scope() {
    assert_eq!(proven(&table(both(true, true)), "client", &MEMBERS), Ok(()));
    let methods = [EntityKind::Method];
    assert_eq!(
        proven(&table(both(false, true)), "client", &methods),
        Ok(())
    );
}

#[test]
fn a_partial_inventory_of_a_listed_kind_names_the_reason_of_the_collector() {
    let found = proven(&table(both(true, false)), "client", &MEMBERS);
    let cause = "closed scope completeness: the member inventory is partial: a member can be added elsewhere";
    assert_eq!(found, Err(cause.to_owned()));
    let literals = [EntityKind::EnumLiteral];
    assert!(proven(&table(both(false, true)), "client", &literals).is_err());
}

#[test]
fn a_kind_without_a_member_inventory_is_not_proven() {
    let found = proven(&table(both(true, true)), "client", &[EntityKind::Function]);
    let cause = "closed scope completeness: no member inventory holds a function";
    assert_eq!(found, Err(cause.to_owned()));
}

#[test]
fn an_owner_without_inventories_or_with_a_missing_kind_is_not_proven() {
    let mut none = table(Vec::new());
    none.inventories.clear();
    assert!(proven(&none, "client", &MEMBERS).is_err());
    let attributes = vec![inventory(MemberKind::Attribute, true, &["token"])];
    assert!(proven(&table(attributes), "client", &MEMBERS).is_err());
    let twice = vec![
        inventory(MemberKind::Method, true, &["run"]),
        inventory(MemberKind::Method, true, &["run"]),
    ];
    assert!(proven(&table(twice), "client", &[EntityKind::Method]).is_err());
}

#[test]
fn a_member_that_the_table_does_not_hold_in_the_owner_is_not_proven() {
    for members in [["run", "gone"], ["run", "other"]] {
        let inventories = vec![
            inventory(MemberKind::Attribute, true, &["token"]),
            inventory(MemberKind::Method, true, &members),
        ];
        let cause =
            "closed scope completeness: a member of the inventory is no entity of the owner";
        assert_eq!(
            proven(&table(inventories), "client", &MEMBERS),
            Err(cause.to_owned())
        );
    }
}
