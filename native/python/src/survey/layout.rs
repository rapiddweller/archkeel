// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The gaps of the files of a survey (AD-450).
//!
//! - One module name in two files: Python imports one of them, by the order of `sys.path` that
//!   the scan does not know (#1000). The survey keeps neither file as a module.
//! - A module whose top package directory lies above its scan root: the parent rule of the scan
//!   receipt does not hold for it.
//! - A stub or compiled module file below a root: Python can import it, the survey cannot read it.
//! - A directory or entry that the snapshot cannot read (#1043).

use std::collections::{BTreeSet, HashMap};

use archkeel_facts::data::GapData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::vocab::Area;
use archkeel_facts::{GapFact, Record};

use super::failures::record;
use crate::module::Module;

pub(super) const DUPLICATE: &str = "duplicate_module";
pub(super) const OUTSIDE_LAYOUT: &str = "module_outside_layout";
pub(super) const FOREIGN: &str = "stub_or_compiled_module";
pub(super) const UNREADABLE: &str = "unreadable_source";
pub(super) const LINKED: &str = "linked_source";

/// The collection gap of one file. Its title is its reason, so the frame names the gap.
fn file_gap(rel: &str, reason: &str) -> Record<GapFact> {
    super::failures::file_gap(rel, reason, reason.to_owned())
}

/// Remove each module whose name another module has too, and give a gap for each such file.
pub(super) fn duplicates(modules: &mut Vec<Module>) -> Vec<Record<GapFact>> {
    let mut files: HashMap<String, Vec<String>> = HashMap::new();
    for module in modules.iter() {
        let paths = files.entry(module.name.clone()).or_default();
        paths.push(module.rel.clone());
    }
    let mut gaps = Vec::new();
    modules.retain(|module| {
        let paths = &files[&module.name];
        if paths.len() < 2 {
            return true;
        }
        let reason = format!(
            "{DUPLICATE}: module {} is in {}",
            module.name,
            paths.join(", ")
        );
        gaps.push(file_gap(&module.rel, &reason));
        false
    });
    gaps
}

/// The path of a module below the directory above its top package.
fn tail(module: &Module) -> String {
    let path = module.name.replace('.', "/");
    if module.is_init() {
        format!("{path}/__init__.py")
    } else {
        format!("{path}.py")
    }
}

/// The parts of a POSIX relative path, without empty and `.` parts.
fn parts(path: &str) -> Vec<&str> {
    path.split('/')
        .filter(|part| !part.is_empty() && *part != ".")
        .collect()
}

/// True when the file is the path of its module and its top package directory is the scan root
/// or lies below it. Then the directory of each package is the parent directory of a file of a
/// direct module, as the scan receipt reads it.
fn in_layout(root: &str, module: &Module) -> bool {
    let tail = tail(module);
    let file = parts(&module.rel);
    let tail_parts = parts(&tail);
    let Some(split) = file.len().checked_sub(tail_parts.len()) else {
        return false;
    };
    if file[split..] != tail_parts[..] {
        return false;
    }
    let mut top: Vec<&str> = file[..split].to_vec();
    top.extend(tail_parts.first());
    top.starts_with(&parts(root))
}

/// A gap for each module that is not in the layout of any scan root.
pub(super) fn outside(modules: &[Module], roots: &[String]) -> Vec<Record<GapFact>> {
    modules
        .iter()
        .filter(|module| !roots.iter().any(|root| in_layout(root, module)))
        .map(|module| {
            let reason = format!(
                "{OUTSIDE_LAYOUT}: the top package of module {} lies above its scan root",
                module.name
            );
            file_gap(&module.rel, &reason)
        })
        .collect()
}

/// A gap for each linked directory below a root: Python imports its modules, the survey does not
/// read them.
pub(super) fn linked(directories: &[String]) -> Vec<Record<GapFact>> {
    directories
        .iter()
        .map(|rel| file_gap(rel, &format!("{LINKED}: {rel}")))
        .collect()
}

/// A gap for each stub or compiled module file.
pub(super) fn foreign(files: &[String]) -> Vec<Record<GapFact>> {
    files
        .iter()
        .map(|rel| file_gap(rel, &format!("{FOREIGN}: {rel}")))
        .collect()
}

/// A gap for each problem of the snapshot: a directory or an entry that it cannot read.
pub(super) fn problems(problems: &BTreeSet<String>) -> Vec<Record<GapFact>> {
    problems
        .iter()
        .map(|problem| {
            let reason = format!("{UNREADABLE}: {problem}");
            let mut data = GapData::at(&reason, "");
            data.module = None;
            let parts = [Part::Text("collection_gap"), Part::Text(&reason)];
            let head = (
                stable_id("COVERAGE", &parts),
                Area::AnalysisCoverage,
                reason,
            );
            record(
                head,
                Vec::new(),
                Vec::new(),
                Vec::new(),
                GapFact::CollectionGap(data),
            )
        })
        .collect()
}

#[cfg(test)]
#[path = "layout_tests.rs"]
mod tests;
