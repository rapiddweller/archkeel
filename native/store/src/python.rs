// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The checks of a Python import survey (AD-450). The store accepts a Python reply only when each
//! claim that can hide an edge agrees with the rest of the reply; its registered sets are the
//! validation block of the collector (AD-688). The generic checks still run on it: coverage counts, inputs, evidence,
//! module bindings and the typed target of each import.

use std::collections::HashSet;

use archkeel_facts::envelope::{Facts, Target};
use archkeel_facts::{ImportFact, Section};

use crate::standard::standard_library_at;

/// The claims of the survey that the model reads for a decision.
pub(crate) fn survey(facts: &Facts) -> Result<(), String> {
    gaps_are_unknowns(facts)?;
    let project: HashSet<&str> = facts
        .files
        .iter()
        .map(|file| first_part(file.module.as_str()))
        .collect();
    let standard = standard_library_at(&facts.validation.standard_library)
        .ok_or("the Python target has no standard library table")?;
    for target in &facts.imports {
        match target {
            Target::Builtin { name, .. } => {
                let top = first_part(name);
                if project.contains(top) || !standard.contains(&top) {
                    return Err(format!("a builtin target must be standard: {name}"));
                }
            }
            Target::External { package, .. } => {
                let name = package.as_str();
                let top = first_part(name);
                if top != name || project.contains(top) || standard.contains(&top) {
                    return Err(format!("an external target must be a package: {name}"));
                }
            }
            Target::Local { .. } | Target::Unresolved { .. } => {}
        }
    }
    facts
        .sections
        .iter()
        .filter_map(|section| match section {
            Section::Imports(records) => Some(records),
            _ => None,
        })
        .flatten()
        .try_for_each(|record| statement(&record.data))
}

/// A Python import is an import statement, or a literal import call (AD-536), with known symbols,
/// no specifier and no type flag. A whole-module import statement whose module object escapes has
/// names that the collector does not read (AD-708).
fn statement(fact: &ImportFact) -> Result<(), String> {
    let (ImportFact::Import(data) | ImportFact::DynamicImport(data)) = fact else {
        return Err("a Python import must be an import statement".to_owned());
    };
    let bare = data.specifier.is_none() && data.type_only.is_none();
    let module_object = matches!(fact, ImportFact::Import(_))
        && data.symbol.is_none()
        && data.binding.is_some();
    if bare && (data.symbols_known || module_object) {
        return Ok(());
    }
    Err("a Python import has no specifier and no type flag".to_owned())
}

/// The coverage gaps are the records of the `unknowns` section, each once: a gap that only one
/// of them names is a partial claim.
pub(crate) fn gaps_are_unknowns(facts: &Facts) -> Result<(), String> {
    let mut unknowns: Vec<&str> = facts
        .sections
        .iter()
        .filter_map(|section| match section {
            Section::Unknowns(records) => Some(records),
            _ => None,
        })
        .flatten()
        .map(|record| record.id.as_str())
        .collect();
    let mut gaps: Vec<&str> = facts
        .coverage
        .gaps
        .iter()
        .map(|gap| gap.id.as_str())
        .collect();
    unknowns.sort_unstable();
    gaps.sort_unstable();
    if unknowns == gaps {
        Ok(())
    } else {
        Err("the coverage gaps must be the unknowns of the survey".to_owned())
    }
}

/// The first segment of a dotted name.
fn first_part(name: &str) -> &str {
    name.split('.').next().unwrap_or(name)
}

#[cfg(test)]
#[path = "python_tests.rs"]
mod tests;
