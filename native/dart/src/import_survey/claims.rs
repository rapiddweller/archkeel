// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The checks of a Dart import survey that only this collector knows (AD-468, AD-688): typed
//! targets that agree with the Dart URI rules, imports and exports with no specifier, and a
//! complete account of each selected input. The core runs them through `archkeel-collect` after
//! the store has validated the reply with its language-free minimum and the validation block (the
//! sections `imports` and `unknowns`), so they can only add rules.

use std::collections::HashSet;

use archkeel_facts::envelope::{Facts, Target};
use archkeel_facts::{GapFact, ImportFact, Section};

/// The claims of the survey that the model reads for a decision.
pub fn check(facts: &Facts) -> Result<(), String> {
    archkeel_facts::surveys::gaps_are_unknowns(facts)?;
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
/// The store checks the owned files themselves (its minimum, AD-688).
fn accounted(facts: &Facts) -> Result<(), String> {
    let owned: HashSet<&str> = facts
        .owned_files
        .iter()
        .map(|file| file.rel_path.as_str())
        .collect();
    let gap_files: HashSet<&str> = facts
        .coverage
        .gaps
        .iter()
        .filter_map(|gap| match &gap.data {
            GapFact::ExceptionGap { data, .. } => data.file.as_deref(),
            _ => None,
        })
        .collect();
    match facts.coverage.selected_files.iter().find(|path| {
        let path = path.as_str();
        let module = facts.files.iter().any(|file| file.rel_path == path);
        !module && !owned.contains(path) && !gap_files.contains(path)
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
mod tests {
    use super::*;

    #[test]
    fn the_first_part_names_the_namespace_of_a_module() {
        assert_eq!(first_part("shop.a"), "shop");
        assert_eq!(first_part("shop"), "shop");
    }
}
