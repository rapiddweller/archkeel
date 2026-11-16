// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the lazy import proof of one module covers (AD-560, AD-654): the leaf that `hazards.rs`,
//! `uses.rs`, `imports.rs`, `routes.rs` and the call count read.

use std::collections::{BTreeMap, HashMap};

use archkeel_facts::ids::ModuleName;
use archkeel_facts::{ImportFact, Record};
use ruff_text_size::TextRange;

/// The value that `__getattr__` returns for a key of its table (AD-654).
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Source {
    /// `getattr(import_module(target), name)`: the attribute `name` of the module `target`.
    Attr(String, String),
    /// `import_module(target)`: the module object itself.
    Module(String),
}

/// What the proof of one module covers: the ranges of the sites that are no gap, the import
/// targets of the calls, and the proven value of each key (AD-654).
#[derive(Default)]
pub(super) struct Lazy {
    pub exempt: Vec<TextRange>,
    pub targets: Vec<(TextRange, String)>,
    pub sources: BTreeMap<String, Source>,
}

/// The proven keys of each lazy module, by module name (AD-654).
pub(crate) type Sources = HashMap<String, BTreeMap<String, Source>>;

/// The proven keys of the modules, in the order of `modules`, by module name.
pub(super) fn by_module<'a>(names: impl Iterator<Item = &'a str>, lazy: &[Lazy]) -> Sources {
    names
        .zip(lazy)
        .filter(|(_, item)| !item.sources.is_empty())
        .map(|(name, item)| (name.to_owned(), item.sources.clone()))
        .collect()
}

/// The import `from module import name` as the module and the symbol that it reads: a proven key
/// reads its source, any other name reads itself.
pub(super) fn view<'a>(
    sources: &'a Sources,
    module: &'a str,
    name: Option<&'a str>,
) -> (&'a str, Option<&'a str>) {
    let found = name.and_then(|name| sources.get(module)?.get(name));
    match found {
        Some(Source::Attr(target, symbol)) => (target, Some(symbol)),
        Some(Source::Module(target)) => (target, None),
        None => (module, name),
    }
}

/// The import records as the values that they bind: the import of a proven key names its source.
/// The edges keep the records; the symbol facts and the call count read this view.
pub(super) fn viewed(imports: &[Record<ImportFact>], sources: &Sources) -> Vec<Record<ImportFact>> {
    let mut out = imports.to_vec();
    for record in &mut out {
        let data = record.data.data();
        let module = data.target_module.as_str();
        let (target, symbol) = view(sources, module, data.symbol.as_deref());
        if target == module {
            continue;
        }
        let (target, symbol) = (ModuleName::new(target), symbol.map(str::to_owned));
        let data = record.data.data_mut();
        data.target_module = target;
        data.symbol = symbol;
    }
    out
}

/// The route hop of each proven attribute key: `P.key` and the `target.name` that it gives.
pub(super) fn links(sources: &Sources) -> impl Iterator<Item = (String, String)> + '_ {
    sources.iter().flat_map(|(module, keys)| {
        keys.iter().filter_map(move |(key, source)| match source {
            Source::Attr(target, name) => {
                Some((format!("{module}.{key}"), format!("{target}.{name}")))
            }
            Source::Module(_) => None,
        })
    })
}
