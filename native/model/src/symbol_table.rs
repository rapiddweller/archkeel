// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol table of a reply (AD-502): the entities of the modules and symbol records, then the
//! edges of the call, reference and base records. The entities (`symbols.rs`) and the edges
//! (`symbol_sites.rs`) do not know this driver.

use archkeel_facts::envelope::Facts;
use archkeel_facts::{Record, Section, SymbolFact};

use crate::ids::{ModuleId, Table};
use crate::modules::Module;
use crate::symbols::{module_id, Entity, Symbols};
use archkeel_contract::EntityKind;

/// The table of the facts of a reply over its modules.
pub(crate) fn derive(facts: &Facts, modules: &Table<ModuleId, Module>) -> Symbols {
    let mut table = Symbols::default();
    for (_, module) in modules.iter() {
        table.push(Entity::named(
            module_id(module.name()),
            EntityKind::Module,
            module.name(),
            vec![module.evidence().to_owned()],
        ));
    }
    let records: &[Record<SymbolFact>] = facts
        .sections
        .iter()
        .find_map(|section| match section {
            Section::Symbols(records) => Some(records.as_slice()),
            _ => None,
        })
        .unwrap_or(&[]);
    table.symbols(records);
    crate::symbol_sites::sites(&mut table, facts, records);
    table
}
