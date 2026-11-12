// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The imports of a reply, split as the reference engine splits them (slice S2).
//!
//! Reference engine: `check/evaluation/imports.py` `split_imports` (an unresolved import and a
//! macro body leave the imports), `check/evaluation/evaluate.py` `evaluate_source` (the external
//! package and the builtin mark of a resolved import) and `ir/import_gaps.py`
//! `derived_unresolved_imports` (an unresolved import whose site no collector gap names).
//!
//! The store accepts a reply only when each import has exactly one typed target, so each
//! import record has its target here.
//!
//! A macro body is not an import of the edges, the cycles or the ranks (AD-349). It stays as a
//! row of its own (`MacroBody`): the fan counts of the modules read it (`count_macro_bodies`).

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::{Facts, Target};
use archkeel_facts::sections::{ImportFact, Section};
use archkeel_facts::vocab::ResolutionDimension;
use archkeel_facts::Record;

/// What the typed target of a resolved import is.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Resolved {
    /// A module of the scanned tree.
    Local,
    /// An external package: its name.
    External(String),
    /// A part of the platform of the language.
    Builtin,
}

/// One resolved import that is not a macro body: the input of the edges and the rules.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Import {
    pub(crate) id: String,
    pub(crate) source_module: String,
    pub(crate) target_module: String,
    pub(crate) source_package: String,
    pub(crate) target_package: String,
    pub(crate) under_type_checking: bool,
    pub(crate) symbol: Option<String>,
    pub(crate) symbols_known: bool,
    pub(crate) relative: bool,
    pub(crate) resolved: Resolved,
    pub(crate) evidence: Vec<String>,
}

impl Import {
    /// The id of the import record.
    pub fn id(&self) -> &str {
        &self.id
    }

    /// The module that imports.
    pub fn source_module(&self) -> &str {
        &self.source_module
    }

    /// The module that the import names.
    pub fn target_module(&self) -> &str {
        &self.target_module
    }

    /// The package of the source module.
    pub fn source_package(&self) -> &str {
        &self.source_package
    }

    /// The package of the target module.
    pub fn target_package(&self) -> &str {
        &self.target_package
    }

    /// True when only a type check reads the import.
    pub fn under_type_checking(&self) -> bool {
        self.under_type_checking
    }

    /// True for a relative import: it resolves inside the scanned tree.
    /// The imported name, or `None` for a whole-module import.
    pub fn symbol(&self) -> Option<&str> {
        self.symbol.as_deref()
    }

    /// True when the collector knows each name that the import uses.
    pub fn symbols_known(&self) -> bool {
        self.symbols_known
    }

    pub fn relative(&self) -> bool {
        self.relative
    }

    /// The typed target.
    pub fn resolved(&self) -> &Resolved {
        &self.resolved
    }

    /// The evidence ids of the import record, sorted.
    pub fn evidence(&self) -> &[String] {
        &self.evidence
    }
}

/// The source and target module of a resolved macro body (`split_imports` templates).
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct MacroBody {
    pub(crate) source_module: String,
    pub(crate) target_module: String,
}

impl MacroBody {
    /// The module that holds the macro body.
    pub(crate) fn source_module(&self) -> &str {
        &self.source_module
    }

    /// The module that the macro body names.
    pub(crate) fn target_module(&self) -> &str {
        &self.target_module
    }
}

/// The imports of a reply, split.
#[derive(Debug, Default)]
pub(crate) struct Split {
    /// The resolved imports that are not macro bodies, in the order of the reply.
    pub(crate) imports: Vec<Import>,
    /// The resolved macro bodies, in the order of the reply.
    pub(crate) macro_bodies: Vec<MacroBody>,
    /// The number of unresolved imports that no collector gap names (each is a coverage
    /// failure of the reference engine).
    pub(crate) unknown: usize,
}

/// Split the imports of a reply. An unresolved import leaves first, then a macro body, as
/// `split_imports` checks them.
pub(crate) fn split(facts: &Facts) -> Split {
    let targets: HashMap<&str, &Target> = facts
        .imports
        .iter()
        .map(|target| (target.import_id().as_str(), target))
        .collect();
    let named: HashSet<(Option<&str>, Vec<&str>)> = facts
        .coverage
        .gaps
        .iter()
        .filter_map(|gap| {
            let data = crate::coverage::data_of(&gap.data);
            (data.resolution_dimension == Some(ResolutionDimension::Imports))
                .then(|| (data.module.as_ref().map(|m| m.as_str()), evidence(gap)))
        })
        .collect();
    let mut found = Split::default();
    for record in facts.sections.iter().flat_map(records) {
        let data = record.data.data();
        let resolved = match targets.get(record.id.as_str()) {
            Some(Target::Unresolved { .. }) => {
                let site = (Some(data.source_module.as_str()), evidence(record));
                found.unknown += usize::from(!named.contains(&site));
                continue;
            }
            _ if matches!(record.data, ImportFact::MacroBody(_)) => {
                found.macro_bodies.push(MacroBody {
                    source_module: data.source_module.as_str().to_owned(),
                    target_module: data.target_module.as_str().to_owned(),
                });
                continue;
            }
            Some(Target::External { package, .. }) => Resolved::External(package.as_str().into()),
            Some(Target::Builtin { .. }) => Resolved::Builtin,
            Some(Target::Local { .. }) | None => Resolved::Local,
        };
        found.imports.push(Import {
            id: record.id.as_str().to_owned(),
            source_module: data.source_module.as_str().to_owned(),
            target_module: data.target_module.as_str().to_owned(),
            source_package: data.source_package.as_str().to_owned(),
            target_package: data.target_package.as_str().to_owned(),
            under_type_checking: data.under_type_checking,
            symbol: data.symbol.clone(),
            symbols_known: data.symbols_known,
            relative: data.relative_level != 0,
            resolved,
            evidence: sorted(evidence(record)),
        });
    }
    found
}

fn records(section: &Section) -> &[Record<ImportFact>] {
    match section {
        Section::Imports(records) => records,
        _ => &[],
    }
}

/// The evidence ids sorted, as `classified` sorts the `evidence_ids` of a row. The site of a
/// gap keeps the order of the reply, as `derived_unresolved_imports` compares it.
fn sorted(mut ids: Vec<&str>) -> Vec<String> {
    ids.sort_unstable();
    ids.into_iter().map(str::to_owned).collect()
}

fn evidence<D>(record: &Record<D>) -> Vec<&str> {
    record.evidence_ids.iter().map(|id| id.as_str()).collect()
}
