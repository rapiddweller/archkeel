// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The checks of a Python import survey that only this collector knows (AD-450, AD-688). The core
//! runs them through `archkeel-collect` after the store has validated the reply with its
//! language-free minimum and the validation block, so they can only add rules: a builtin target
//! is a module of the standard library of the target, an external target is a package outside the
//! project and the standard library, and each import is an import statement or a literal import
//! call with known symbols, no specifier and no type flag.

use std::collections::HashSet;

use archkeel_facts::envelope::{Facts, Target};
use archkeel_facts::{ImportFact, Section};

/// The claims of the survey that the model reads for a decision.
pub fn check(facts: &Facts) -> Result<(), String> {
    archkeel_facts::surveys::gaps_are_unknowns(facts)?;
    let project: HashSet<&str> = facts
        .files
        .iter()
        .map(|file| first_part(file.module.as_str()))
        .collect();
    let standard = standard_library(&facts.validation.standard_library)
        .ok_or("the Python target has no standard library table")?;
    for target in &facts.imports {
        match target {
            Target::Builtin { name, .. } => {
                let top = first_part(name);
                if project.contains(top) || !standard.contains(top) {
                    return Err(format!("a builtin target must be standard: {name}"));
                }
            }
            Target::External { package, .. } => {
                let name = package.as_str();
                let top = first_part(name);
                if top != name || project.contains(top) || standard.contains(top) {
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

/// The pinned list of the key of the reply (`archkeel-python-analyzer@3.12`), or none when the
/// key has no list.
fn standard_library(key: &str) -> Option<HashSet<&'static str>> {
    let names: HashSet<&'static str> = archkeel_facts::STANDARD_LIBRARY
        .lines()
        .filter_map(|line| line.split_once(' '))
        .filter_map(|(owner, name)| (owner == key).then_some(name))
        .collect();
    (!names.is_empty()).then_some(names)
}

/// A Python import is an import statement, or a literal import call (AD-536), with known symbols,
/// no specifier and no type flag. A whole-module import statement whose module object escapes has
/// names that the collector does not read (AD-708).
fn statement(fact: &ImportFact) -> Result<(), String> {
    let (ImportFact::Import(data) | ImportFact::DynamicImport(data)) = fact else {
        return Err("a Python import must be an import statement".to_owned());
    };
    let bare = data.specifier.is_none() && data.type_only.is_none();
    let module_object =
        matches!(fact, ImportFact::Import(_)) && data.symbol.is_none() && data.binding.is_some();
    if bare && (data.symbols_known || module_object) {
        return Ok(());
    }
    Err("a Python import has no specifier and no type flag".to_owned())
}

/// The first segment of a dotted name.
fn first_part(name: &str) -> &str {
    name.split('.').next().unwrap_or(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_first_part_names_the_package() {
        assert_eq!(first_part("os.path"), "os");
        assert_eq!(first_part("app"), "app");
    }

    #[test]
    fn a_key_without_a_list_has_no_standard_library() {
        assert!(standard_library("archkeel-python-analyzer@3.12").is_some_and(|n| n.contains("os")));
        assert!(standard_library("archkeel-python-analyzer@3.10").is_none());
    }
}
