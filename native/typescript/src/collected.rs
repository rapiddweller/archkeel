// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one collection, before the producer of the reply writes the records of the
//! sections that come after the imports (`records::plan`), and the lists of records that the
//! tests and the dump read.

use archkeel_facts::envelope::{Evidence, FileFact, Input, Provenance, Target};
use archkeel_facts::{
    BindingFact, ConstructFact, GapFact, ImportFact, IntoSection, Record, Section,
};
use serde_json::Value;

/// The facts of one collection, in the order the reply writes them.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Facts {
    pub provenance: Provenance,
    pub git_head: String,
    pub dirty: Value,
    pub scope: Vec<String>,
    pub sections: Vec<Section>,
    pub features: Vec<&'static str>,
    /// The construct capabilities: `(name, status)`, for example `("string_literal_compare", "partial")`.
    pub constructs: Vec<(&'static str, &'static str)>,
    pub inputs: Vec<Input>,
    pub files: Vec<FileFact>,
    /// The resolved target of each import record, in the order of the walk.
    pub imports: Vec<Target>,
    pub selected_files: Vec<String>,
    pub files_read: usize,
    /// Coverage gaps. The collection is complete only when there is none.
    pub gaps: Vec<Record<GapFact>>,
    pub evidence: Vec<Evidence>,
}

/// An import record of archkeel-facts (AD-345).
pub(crate) type ImportRecord = Record<ImportFact>;

/// The records of this phase, as the Python collector builds them.
#[derive(Default)]
pub(crate) struct Records {
    /// All import records, sorted by id: a statement with bound names is replaced by one record for
    /// each name.
    pub imports: Vec<ImportRecord>,
    /// The targets in the order of the walk, with the expanded statements in place.
    pub targets: Vec<Target>,
    /// The `ESM_EXPORT` records that the expanded imports cite, in the order of their first use.
    pub witnesses: Vec<Record<BindingFact>>,
    /// The `TSCONSTRUCT` records, sorted by id.
    pub constructs: Vec<Record<ConstructFact>>,
    /// The `TSDEF` records, in the order of the symbol table (PR 4.3a-3b).
    #[cfg(any(test, feature = "dump"))]
    pub symbols: Vec<Record<archkeel_facts::SymbolFact>>,
    /// The `TSCALL`, `TSREF` and result binding records (PR 4.3a-3c).
    #[cfg(any(test, feature = "dump"))]
    pub calls: Vec<Record<archkeel_facts::CallFact>>,
    #[cfg(any(test, feature = "dump"))]
    pub references: Vec<Record<archkeel_facts::ReferenceFact>>,
    #[cfg(any(test, feature = "dump"))]
    pub bindings: Vec<Record<BindingFact>>,
    /// The ids of the evidence that the records above cite.
    #[cfg(feature = "dump")]
    pub touched: Vec<String>,
}

/// `classified`: the subjects without empty names, sorted; the evidence ids sorted.
pub(crate) fn sorted(mut values: Vec<String>) -> Vec<String> {
    values.sort();
    values
}

/// The typed import records of the facts.
pub(crate) fn import_section(facts: &Facts) -> &[ImportRecord] {
    facts
        .sections
        .iter()
        .find_map(ImportFact::records)
        .unwrap_or_default()
}
