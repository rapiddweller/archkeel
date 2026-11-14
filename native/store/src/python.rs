// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The checks of a Python import survey (AD-450). The store accepts a Python reply only as the
//! import survey of protocol 10.0.0, and only when each claim that can hide an edge agrees with
//! the rest of the reply. The generic checks still run on it: coverage counts, inputs, evidence,
//! module bindings and the typed target of each import.

use std::collections::HashSet;

use archkeel_facts::envelope::{Facts, LimitSupport, Profile, ProtocolVersion, Target};
use archkeel_facts::{ImportFact, Section};

use crate::standard::standard_library_everywhere;

/// The protocol of a profile: 10.0.0 is the Python survey, and Python has no other protocol.
pub(crate) fn version(version: ProtocolVersion, profile: Profile) -> Result<(), String> {
    match (version, profile) {
        (ProtocolVersion::V10, Profile::Python) => Ok(()),
        (ProtocolVersion::V10, _) => {
            Err("protocol 10.0.0 is only the Python import survey (AD-450)".to_owned())
        }
        (_, Profile::Python) => {
            Err("a Python reply must be the 10.0.0 import survey (AD-450)".to_owned())
        }
        _ => Ok(()),
    }
}

/// The registered set of an import survey (Python, AD-450; Dart, AD-468): the sections `imports` and `unknowns`, no construct, and no
/// statement that interfaces are supported. `validate::checkable` refuses each resolution feature
/// of a Python reply, and `registered.rs` binds the symbol statement to its feature.
pub(crate) fn registered(facts: &Facts) -> Result<(), String> {
    let mut sections: Vec<&str> = facts
        .capabilities
        .sections
        .iter()
        .map(|name| name.as_str())
        .collect();
    sections.sort_unstable();
    if sections != ["imports", "unknowns"] || !facts.capabilities.constructs.is_empty() {
        return Err(format!(
            "a {} reply must be exactly the import survey (AD-450, AD-468)",
            facts.profile.as_str()
        ));
    }
    let interface = facts.profile_limits.map(|limits| limits.interface_boundary);
    // AD-504: the Python survey writes the publication routes; the Dart survey does not.
    if interface == Some(LimitSupport::Supported) && facts.profile != Profile::Python {
        return Err("the import survey supports no interface rule".to_owned());
    }
    Ok(())
}

/// The claims of the survey that the model reads for a decision.
pub(crate) fn survey(facts: &Facts) -> Result<(), String> {
    gaps_are_unknowns(facts)?;
    let project: HashSet<&str> = facts
        .files
        .iter()
        .map(|file| first_part(file.module.as_str()))
        .collect();
    let standard = standard_library_everywhere(Profile::Python);
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

/// A Python import is an import statement with known symbols, no specifier and no type flag.
fn statement(fact: &ImportFact) -> Result<(), String> {
    if !matches!(fact, ImportFact::Import(_)) {
        return Err("a Python import must be an import statement".to_owned());
    }
    let data = fact.data();
    if data.specifier.is_some() || data.type_only.is_some() || !data.symbols_known {
        return Err("a Python import has no specifier and no type flag".to_owned());
    }
    Ok(())
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
