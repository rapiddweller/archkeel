// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The checks of a Dart import survey (AD-468). The store accepts a Dart reply only as the import
//! survey of one package (AD-454): the sections `imports` and `unknowns`, typed targets that
//! agree with the Dart URI rules, and a complete account of each selected input. The generic
//! checks still run on it: coverage counts, inputs, evidence and module bindings.

use std::collections::HashSet;

use archkeel_facts::envelope::{Facts, Target};
use archkeel_facts::{GapFact, ImportFact, Section};

/// The claims of the survey that the model reads for a decision.
pub(crate) fn survey(facts: &Facts) -> Result<(), String> {
    crate::python::gaps_are_unknowns(facts)?;
    let project: HashSet<&str> = facts
        .files
        .iter()
        .map(|file| first_part(file.module.as_str()))
        .collect();
    facts
        .imports
        .iter()
        .try_for_each(|target| self::target(target, &project))?;
    facts
        .sections
        .iter()
        .filter_map(|section| match section {
            Section::Imports(records) => Some(records),
            _ => None,
        })
        .flatten()
        .try_for_each(|record| statement(&record.data))?;
    accounted(facts)
}

/// A built-in target is one `dart:` library; an external target is one package that is not the
/// namespace of the project. A survey writes no unresolved target: it writes a gap.
fn target(target: &Target, project: &HashSet<&str>) -> Result<(), String> {
    match target {
        Target::Builtin { name, .. } => {
            let library = name.strip_prefix("dart.").unwrap_or("");
            if library.is_empty() || library.contains('.') {
                return Err(format!(
                    "a Dart builtin target must be one dart: library: {name}"
                ));
            }
        }
        Target::External { package, .. } => {
            let name = package.as_str();
            if name.is_empty() || name.contains('.') || project.contains(name) {
                return Err(format!(
                    "a Dart external target must be another package: {name}"
                ));
            }
        }
        Target::Local { .. } => {}
        Target::Unresolved { .. } => {
            return Err("a Dart survey writes a gap, not an unresolved target".to_owned());
        }
    }
    Ok(())
}

/// A Dart import is an import or an export statement with no specifier and no type flag.
fn statement(fact: &ImportFact) -> Result<(), String> {
    if !matches!(fact, ImportFact::Import(_) | ImportFact::Reexport(_)) {
        return Err("a Dart import must be an import or an export".to_owned());
    }
    let data = fact.data();
    if data.specifier.is_some() || data.type_only.is_some() || data.symbols_known {
        return Err("a Dart import has no specifier, no type flag and no known symbols".to_owned());
    }
    Ok(())
}

/// Each selected input is the file of a module, a part with a named owner, or the file of a gap.
/// An owned file is not a module file, its owner is a module, and its own module is no module.
fn accounted(facts: &Facts) -> Result<(), String> {
    let modules: HashSet<&str> = facts
        .files
        .iter()
        .map(|file| file.module.as_str())
        .collect();
    let module_files: HashSet<&str> = facts
        .files
        .iter()
        .map(|file| file.rel_path.as_str())
        .collect();
    let mut owned: HashSet<&str> = HashSet::new();
    for file in &facts.owned_files {
        if module_files.contains(file.rel_path.as_str())
            || !modules.contains(file.owner.as_str())
            || modules.contains(file.module.as_str())
            || !owned.insert(file.rel_path.as_str())
        {
            return Err(format!(
                "the owned file {} has no unique owner",
                file.rel_path
            ));
        }
    }
    let gap_files: HashSet<&str> = facts
        .coverage
        .gaps
        .iter()
        .filter_map(|gap| match &gap.data {
            GapFact::ExceptionGap { data, .. } => data.file.as_deref(),
            _ => None,
        })
        .collect();
    let selected = &facts.coverage.selected_files;
    if !owned
        .iter()
        .all(|path| selected.iter().any(|item| item == path))
    {
        return Err("an owned file needs a selected input".to_owned());
    }
    match selected.iter().find(|path| {
        let path = path.as_str();
        !module_files.contains(path) && !owned.contains(path) && !gap_files.contains(path)
    }) {
        Some(path) => Err(format!(
            "the selected file {path} has no module, owner or gap"
        )),
        None => Ok(()),
    }
}

/// The first segment of a dotted name.
fn first_part(name: &str) -> &str {
    name.split('.').next().unwrap_or(name)
}

#[cfg(test)]
#[path = "dart_tests.rs"]
mod tests;
