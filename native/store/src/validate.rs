// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The generic validation of a reply: the language-neutral checks of
//! `ir/facts_validation.py:validate_source_facts` (lines 5716-6204), run once (AD-346).
//!
//! The messages are the messages of the Python checks, so a diagnostic does not change. This file
//! checks the envelope: coverage counts, unique ids, inputs, evidence paths and ranges, file
//! evidence, sections against capabilities and the features that the store can check.
//! `validate_records` checks the records and `bindings` binds each record to its module.

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::{Facts, Profile, Role};
use archkeel_facts::identity::inside;

/// The resolution features of the profiles whose records the store checks completely.
const TYPESCRIPT_FEATURES: [&str; 8] = [
    "static-imports",
    "literal-imports",
    "relative-specifiers",
    "node-builtins",
    "local-runtime-closure",
    "inner-uml-v1",
    "script-globals-v1",
    "bundler-mode-v1",
];

/// `_unique` of the Python checks: no duplicate and no empty value.
pub(crate) fn unique<'a, I: IntoIterator<Item = &'a str>>(
    values: I,
    label: &str,
) -> Result<HashSet<&'a str>, String> {
    let mut seen = HashSet::new();
    let mut count = 0usize;
    let mut empty = false;
    for value in values {
        count += 1;
        empty |= value.is_empty();
        seen.insert(value);
    }
    if seen.len() != count {
        return Err(format!("duplicate {label}"));
    }
    if empty {
        return Err(format!("empty {label}"));
    }
    Ok(seen)
}

fn relative(path: &str, label: &str) -> Result<(), String> {
    if inside(path) {
        Ok(())
    } else {
        Err(format!("{label} must stay inside the snapshot"))
    }
}

fn digest(text: &str, label: &str) -> Result<(), String> {
    let hex = text
        .bytes()
        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte));
    if text.len() == 64 && hex {
        Ok(())
    } else {
        Err(format!("{label} must be a SHA-256 digest"))
    }
}

/// The checks of the Python decoder that serde does not make: relative paths and digests.
fn decoder_checks(facts: &Facts) -> Result<(), String> {
    digest(&facts.adapter.code_digest, "adapter.code_digest")?;
    digest(&facts.source.source_digest, "source.source_digest")?;
    for input in &facts.inputs {
        relative(&input.path, "input.path")?;
        digest(&input.digest, "input.digest")?;
    }
    for file in &facts.files {
        relative(&file.rel_path, "file.rel_path")?;
    }
    for path in &facts.coverage.selected_files {
        relative(path, "coverage.selected_files")?;
    }
    for target in &facts.imports {
        if let archkeel_facts::envelope::Target::Local {
            file,
            runtime_file,
            declaration_file,
            ..
        } = target
        {
            relative(file, "target.file")?;
            for path in [runtime_file, declaration_file].into_iter().flatten() {
                relative(path, "target.runtime_file")?;
            }
        }
    }
    Ok(())
}

/// The store checks only the replies whose every claim it can check (AD-346).
fn checkable(facts: &Facts) -> Result<(), String> {
    match facts.profile {
        Profile::TypeScript => {}
        Profile::Python | Profile::Dart => {
            return Err(format!(
                "the store does not check {} replies yet",
                facts.profile.as_str()
            ))
        }
    }
    for feature in &facts.capabilities.resolution_features {
        if !TYPESCRIPT_FEATURES.contains(&feature.as_str()) {
            return Err(format!(
                "the store does not check the resolution feature {feature} yet"
            ));
        }
    }
    Ok(())
}

fn coverage_checks(facts: &Facts) -> Result<HashSet<&str>, String> {
    let coverage = &facts.coverage;
    let selected = unique(
        coverage.selected_files.iter().map(String::as_str),
        "selected file",
    )?;
    let count = selected.len() as u64;
    if !(coverage.files_parsed <= coverage.files_read && coverage.files_read <= count) {
        return Err("impossible collection coverage counts".to_owned());
    }
    let gaps = !coverage.gaps.is_empty();
    if coverage.files_parsed < count && !gaps {
        return Err("unobserved selected files require coverage gaps".to_owned());
    }
    if !coverage.full_scope && !gaps {
        return Err("partial collection requires coverage gaps".to_owned());
    }
    if coverage.full_scope && (gaps || coverage.files_parsed != count) {
        return Err("complete collection contradicts coverage gaps or counts".to_owned());
    }
    Ok(selected)
}

/// The facts that the record checks read: the ids, the inputs and the selected inputs.
pub(crate) struct Envelope<'a> {
    pub(crate) inputs: HashSet<&'a str>,
    pub(crate) selected_inputs: HashSet<&'a str>,
    pub(crate) file_ids: HashSet<&'a str>,
    pub(crate) evidence_ids: HashSet<&'a str>,
    pub(crate) features: HashSet<&'a str>,
}

/// The sets that the record checks read. They are taken from an envelope that `envelope` checked.
pub(crate) fn index(facts: &Facts) -> Envelope<'_> {
    Envelope {
        inputs: facts.inputs.iter().map(|item| item.path.as_str()).collect(),
        selected_inputs: facts
            .inputs
            .iter()
            .filter(|item| item.role == Role::Selected)
            .map(|item| item.path.as_str())
            .collect(),
        file_ids: facts.files.iter().map(|item| item.id.as_str()).collect(),
        evidence_ids: facts.evidence.iter().map(|item| item.id.as_str()).collect(),
        features: facts
            .capabilities
            .resolution_features
            .iter()
            .map(String::as_str)
            .collect(),
    }
}

/// The envelope checks. They run on the typed reply, before its records are converted.
/// `names` are the section names of the reply, in reply order.
pub(crate) fn envelope(facts: &Facts, names: &[&str]) -> Result<(), String> {
    decoder_checks(facts)?;
    checkable(facts)?;
    let selected = coverage_checks(facts)?;
    let inputs = unique(
        facts.inputs.iter().map(|item| item.path.as_str()),
        "resolution input",
    )?;
    let selected_inputs: HashSet<&str> = facts
        .inputs
        .iter()
        .filter(|item| item.role == Role::Selected)
        .map(|item| item.path.as_str())
        .collect();
    if !selected_inputs.is_subset(&selected) {
        return Err("selected input is outside selected coverage".to_owned());
    }
    unique(facts.files.iter().map(|item| item.id.as_str()), "file id")?;
    unique(
        facts.files.iter().map(|item| item.module.as_str()),
        "module identity",
    )?;
    if !facts
        .files
        .iter()
        .all(|item| selected_inputs.contains(item.rel_path.as_str()))
    {
        return Err("observed module needs a selected input".to_owned());
    }
    let files = facts.files.len() as u64;
    if files > facts.coverage.files_parsed {
        return Err("observed modules exceed parsed files".to_owned());
    }
    if facts.profile != Profile::Dart && files != facts.coverage.files_parsed {
        return Err("each parsed source file needs an observed module".to_owned());
    }
    if facts.coverage.full_scope && facts.coverage.files_parsed > 0 && files == 0 {
        return Err("complete parsed source needs an observed module".to_owned());
    }
    unique(
        facts.evidence.iter().map(|item| item.id.as_str()),
        "evidence id",
    )?;
    evidence_checks(facts, &inputs)?;
    capability_checks(facts, names)
}

fn evidence_checks(facts: &Facts, inputs: &HashSet<&str>) -> Result<(), String> {
    for entry in &facts.evidence {
        if !inside(&entry.file) {
            return Err("evidence path escapes source snapshot".to_owned());
        }
        if !inputs.contains(entry.file.as_str()) {
            return Err("evidence needs a digested input".to_owned());
        }
        if entry.line < 0 || entry.end_line < entry.line || entry.column < 0 {
            return Err("invalid evidence range".to_owned());
        }
    }
    let by_id: HashMap<&str, &str> = facts
        .evidence
        .iter()
        .map(|item| (item.id.as_str(), item.file.as_str()))
        .collect();
    for file in &facts.files {
        match by_id.get(file.evidence_id.as_str()) {
            None => return Err("file has dangling evidence reference".to_owned()),
            Some(path) if *path != file.rel_path => {
                return Err("module evidence disagrees with source file".to_owned())
            }
            Some(_) => {}
        }
    }
    Ok(())
}

fn capability_checks(facts: &Facts, names: &[&str]) -> Result<(), String> {
    let names = unique(names.iter().copied(), "section")?;
    let capabilities = &facts.capabilities;
    let declared = unique(
        capabilities.sections.iter().map(|name| name.as_str()),
        "capability section",
    )?;
    unique(
        capabilities.resolution_features.iter().map(String::as_str),
        "resolution feature",
    )?;
    unique(
        capabilities
            .constructs
            .iter()
            .map(|entry| entry.name.as_str()),
        "construct capability",
    )?;
    if names != declared {
        return Err("source sections disagree with declared capabilities".to_owned());
    }
    Ok(())
}

#[cfg(test)]
#[path = "validate_tests.rs"]
mod tests;
