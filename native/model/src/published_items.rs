// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The public module-level items of a reply (AD-670): each symbol at module level that the
//! collector states as declared public. The graph reads them when a rule needs them; the rule
//! (`published.rs`) judges them.

use archkeel_contract::PublicItemKind;
use archkeel_facts::envelope::Facts;
use archkeel_facts::{Record, Section, SymbolFact};

/// One public module-level item of the reply.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PublicItem {
    /// The module that defines it.
    pub module: String,
    /// Its name.
    pub name: String,
    /// Its kind, as the symbol facts name it.
    pub kind: PublicItemKind,
    /// The evidence of its definition.
    pub evidence: Vec<String>,
    /// False when the collector does not read the name: a macro call gives it (AD-718).
    pub named: bool,
}

/// The kind of a symbol record; a method is a member, not an item.
fn kind_of(fact: &SymbolFact) -> Option<PublicItemKind> {
    Some(match fact {
        SymbolFact::Class(_) => PublicItemKind::Class,
        SymbolFact::Function(_) => PublicItemKind::Function,
        SymbolFact::Method(_) => return None,
        SymbolFact::Constant(_) => PublicItemKind::Constant,
        SymbolFact::TypeAlias(_) => PublicItemKind::TypeAlias,
        SymbolFact::Binding(_) => PublicItemKind::Binding,
        SymbolFact::Alias(_) => PublicItemKind::Alias,
        SymbolFact::DynamicBinding(_) => PublicItemKind::DynamicBinding,
        SymbolFact::StaticConstant(_) => PublicItemKind::StaticConstant,
        SymbolFact::Macro(_) => PublicItemKind::Macro,
        // A module-level variable is a binding of its module.
        SymbolFact::Attribute(_) => PublicItemKind::Binding,
    })
}

/// The public module-level items of the symbol facts, in reply order.
pub(crate) fn items(facts: &Facts) -> Vec<PublicItem> {
    let records: &[Record<SymbolFact>] = facts
        .sections
        .iter()
        .find_map(|section| match section {
            Section::Symbols(records) => Some(records.as_slice()),
            _ => None,
        })
        .unwrap_or(&[]);
    records.iter().filter_map(item).collect()
}

/// The module, name, parent and visibility of a symbol record, whatever its kind: the parent is
/// reduced to whether the symbol is at module level.
fn fields(fact: &SymbolFact) -> (&str, &str, bool, &str, &str) {
    let (module, name, parent, visibility) = match fact {
        SymbolFact::Class(d) => (&d.module, &d.name, &d.parent, &d.visibility_detail),
        SymbolFact::Function(d) | SymbolFact::Method(d) => {
            (&d.module, &d.name, &d.parent, &d.visibility_detail)
        }
        SymbolFact::Constant(d)
        | SymbolFact::TypeAlias(d)
        | SymbolFact::Binding(d)
        | SymbolFact::Alias(d)
        | SymbolFact::DynamicBinding(d)
        | SymbolFact::StaticConstant(d)
        | SymbolFact::Macro(d)
        | SymbolFact::Attribute(d) => (&d.module, &d.name, &d.parent, &d.visibility_detail),
    };
    (
        module.as_str(),
        name,
        parent.is_none(),
        &visibility.kind,
        &visibility.basis,
    )
}

/// The module and name of each module-level symbol of the reply, whatever its visibility
/// (AD-1048): a `target_symbol` that is declared in no module is a typo.
pub(crate) fn declared(facts: &Facts) -> std::collections::HashSet<(String, String)> {
    facts
        .sections
        .iter()
        .filter_map(|section| match section {
            Section::Symbols(records) => Some(records),
            _ => None,
        })
        .flatten()
        .filter_map(|record| {
            let (module, name, top, _, _) = fields(&record.data);
            top.then(|| (module.to_owned(), name.to_owned()))
        })
        .collect()
}

fn item(record: &Record<SymbolFact>) -> Option<PublicItem> {
    let kind = kind_of(&record.data)?;
    let (module, name, top, visibility, basis) = fields(&record.data);
    let named = basis != "macro_call";
    (top && visibility == "public").then(|| PublicItem {
        named,
        module: module.to_owned(),
        name: name.to_owned(),
        kind,
        evidence: record
            .evidence_ids
            .iter()
            .map(|id| id.as_str().to_owned())
            .collect(),
    })
}
