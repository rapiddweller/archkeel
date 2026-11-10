// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol records of PR 4.3a-3b: one `TSDEF` record for each definition
//! (`_inner_symbols`, `_symbol_metadata`).
//!
//! The reply carries them under the capability `inner-uml-v1` (AD-340). The `dump` feature prints them, and
//! `tests/test_collector_native_records.py` compares them with the unmodified Python collector.

use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::nested::VisibilityDetail;
use archkeel_facts::vocab::{Area, EvidenceClass, SymbolCategory};
use archkeel_facts::{Record, SymbolFact};

use crate::cited::Cited;
use crate::class_data::{
    callable_data, class_data, classifier, decorators, value_data, visibility, Core, Methods,
};
use crate::definitions::DefinitionKind;
use crate::symbol_table::{Entry, SymbolTable};

fn methods_of(table: &SymbolTable) -> Methods {
    let mut found = Methods::new();
    for entry in &table.entries {
        let definition = entry.definition;
        let (Some(parent), Some(line), Some(column)) = (
            entry.parent,
            definition.parent_line,
            definition.parent_column,
        ) else {
            continue;
        };
        if definition.kind == DefinitionKind::Method {
            let key = (entry.module.to_owned(), parent.to_owned(), line, column);
            found.entry(key).or_default().push(entry.id.clone());
        }
    }
    found
}

/// The records of all definitions, in the order of the table, one at a time: a record is written
/// and dropped, so the records of a whole project are never alive together.
pub fn each(table: &SymbolTable, cited: &mut Cited, emit: &mut dyn FnMut(Record<SymbolFact>)) {
    let methods = methods_of(table);
    for entry in &table.entries {
        emit(record(table, &methods, cited, entry));
    }
}

/// The `symbol_category` of a definition: a class, an interface and an enum are all `class`.
fn category(kind: DefinitionKind) -> SymbolCategory {
    match kind {
        DefinitionKind::Class | DefinitionKind::Interface | DefinitionKind::Enum => {
            SymbolCategory::Class
        }
        DefinitionKind::Method => SymbolCategory::Method,
        DefinitionKind::Function => SymbolCategory::Function,
        DefinitionKind::TypeAlias => SymbolCategory::TypeAlias,
        DefinitionKind::Constant => SymbolCategory::Constant,
    }
}

/// `_inner_symbols` for one definition.
fn record(
    table: &SymbolTable,
    methods: &Methods,
    cited: &mut Cited,
    entry: &Entry,
) -> Record<SymbolFact> {
    let definition = entry.definition;
    let evidence = cited.cite(entry.rel, &definition.span);
    let core = metadata(table, cited, entry);
    let data = match definition.kind {
        DefinitionKind::Class | DefinitionKind::Interface | DefinitionKind::Enum => {
            let more = classifier(table, methods, cited, entry);
            SymbolFact::Class(class_data(core, more))
        }
        DefinitionKind::Function => SymbolFact::Function(callable_data(core, entry)),
        DefinitionKind::Method => SymbolFact::Method(callable_data(core, entry)),
        DefinitionKind::TypeAlias => SymbolFact::TypeAlias(value_data(core, entry)),
        DefinitionKind::Constant => SymbolFact::Constant(value_data(core, entry)),
    };
    Record {
        id: FactId::new(&entry.id),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: format!("{} declaration", entry.qualified),
        subjects: vec![entry.qualified.to_string()],
        evidence_ids: vec![EvidenceId::new(evidence)],
        fact_ids: Vec::new(),
        data,
    }
}

/// `_symbol_metadata`.
fn metadata(table: &SymbolTable, cited: &mut Cited, entry: &Entry) -> Core {
    let definition = entry.definition;
    let parent_id = match (definition.parent_line, definition.parent_column) {
        (Some(line), Some(column)) if entry.parent.is_some() => entry
            .parent_qualified()
            .and_then(|name| table.scope(&name, line, column))
            .map(|parent| FactId::new(&parent.id)),
        _ => None,
    };
    let unknown = definition.top_level && definition.visibility.is_none();
    let kind = match definition.visibility {
        Some(item) => visibility(item),
        None if definition.top_level => "unknown",
        None => "public",
    };
    let (decorators, decorator_evidence_ids) =
        decorators(cited, entry.rel, &definition.decorator_sources);
    Core {
        qualified_name: entry.qualified.to_string(),
        module: ModuleName::new(entry.module),
        package: PackageName::new(entry.package()),
        name: definition.name.clone(),
        parent: entry.parent_qualified(),
        lexical_parent_id: parent_id,
        visibility_detail: VisibilityDetail {
            basis: if unknown { "unknown" } else { "language" }.to_owned(),
            kind: kind.to_owned(),
            spelling: definition.name.clone(),
        },
        symbol_category: category(definition.kind),
        source_binding_unique: table.count(&entry.qualified) == 1,
        decorators,
        decorator_evidence_ids,
        signature_complete: definition.signature_complete,
        overload_signature: definition.overload_signature,
    }
}

#[cfg(test)]
#[path = "symbols_tests.rs"]
mod tests;
