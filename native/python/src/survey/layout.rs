// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The gaps of the files of a survey (AD-450).
//!
//! - One module name in two files: Python imports one of them, by the order of `sys.path` that
//!   the scan does not know (#1000). The survey keeps neither file as a module.
//! - A module whose top package directory lies above its scan root: the parent rule of the scan
//!   receipt does not hold for it.
//! - A script file (a name that no import can spell) is no module: it has no layout and no gap.
//! - A stub or compiled module file below a root: Python can import it, the survey cannot read it.
//! - A directory or entry that the snapshot cannot read (#1043).

use std::collections::{BTreeSet, HashMap, HashSet};

use archkeel_facts::data::GapData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::pyminor::PyMinor;
use archkeel_facts::vocab::Area;
use archkeel_facts::{GapFact, Record};

use super::effects::AMBIGUOUS_ROOTS;
use super::failures::record;
use crate::module::{first_part, Module};
use crate::names::{below_root, importable_path, scoped};

pub(super) const DUPLICATE: &str = "duplicate_module";
pub(super) const OUTSIDE_LAYOUT: &str = "module_outside_layout";
pub(super) const FOREIGN: &str = "stub_or_compiled_module";
pub(super) const UNREADABLE: &str = "unreadable_source";
pub(super) const LINKED: &str = "linked_source";

/// The collection gap of one file. Its title is its reason, so the frame names the gap.
fn file_gap(rel: &str, reason: &str) -> Record<GapFact> {
    super::failures::file_gap(rel, reason, reason.to_owned())
}

pub(super) fn gaps(
    modules: &mut Vec<Module>,
    (selected, unsupported, links): (&[String], &[String], &[String]),
    (namespace, roots): (&str, &[String]),
    uncertain_manifest: Option<&str>,
) -> Vec<Record<GapFact>> {
    let mut found = if namespace.is_empty() {
        ambiguous_roots(modules, selected, roots)
    } else {
        duplicates(modules)
    };
    if let Some(manifest) = uncertain_manifest {
        found.push(file_gap(
            manifest,
            &format!("{AMBIGUOUS_ROOTS}: the available files do not establish the runtime Python import roots"),
        ));
    }
    found.extend(outside(modules, roots));
    found.extend(foreign(unsupported));
    found.extend(linked(links));
    found
}

/// Remove each module whose name another module has too, and give a gap for each such file.
fn duplicates(modules: &mut Vec<Module>) -> Vec<Record<GapFact>> {
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

/// The first name of each package or module that the scan can supply, including failed reads.
pub(super) fn project_names(
    selected: &[String],
    namespace: &str,
    roots: &[String],
    minor: PyMinor,
) -> HashSet<String> {
    if !namespace.is_empty() {
        return HashSet::from([first_part(namespace).to_owned()]);
    }
    selected
        .iter()
        .filter_map(|path| {
            scoped(path, namespace, roots, minor).filter(|name| importable_path(path, name))
        })
        .map(|name| first_part(&name).to_owned())
        .collect()
}

/// A regular package or a module in one root can shadow all children of a package in another.
fn ambiguous_roots(
    modules: &mut Vec<Module>,
    selected: &[String],
    roots: &[String],
) -> Vec<Record<GapFact>> {
    let mut providers: HashMap<&str, BTreeSet<&str>> = HashMap::new();
    for path in selected {
        let Some((root, relative)) = roots
            .iter()
            .find_map(|root| below_root(path, root).map(|relative| (root, relative)))
        else {
            continue;
        };
        let top = relative
            .split_once('/')
            .map(|(top, _)| top)
            .or_else(|| relative.strip_suffix(".py"));
        if let Some(top) = top.filter(|top| archkeel_facts::identity::is_identifier(top)) {
            providers.entry(top).or_default().insert(root);
        }
    }
    let mut gaps = Vec::new();
    modules.retain(|module| {
        let top = first_part(&module.name);
        let Some(found) = providers.get(top).filter(|found| found.len() > 1) else {
            return true;
        };
        let directories = found.iter().copied().collect::<Vec<_>>().join(", ");
        let reason = format!("{DUPLICATE}: {top} has providers in {directories}");
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

/// True when no import statement can name the file: it is a script, not a module (AD-648).
///
/// A part of its dotted name is no identifier (`demo-custom-components`), or its stem holds a dot
/// (`converter.scr.py`: `import pkg.converter.scr` looks for `pkg/converter/scr.py`). Python runs such
/// a file only when a loader is given its path, and a loader call is its own gap. The imports
/// that the script writes are still edges of its file.
pub(super) fn is_script(module: &Module) -> bool {
    let stem = module.rel.rsplit('/').next().unwrap_or(&module.rel);
    let stem = stem.strip_suffix(".py").unwrap_or(stem);
    stem.contains('.')
        || !module
            .name
            .split('.')
            .all(archkeel_facts::identity::is_identifier)
}

/// A gap for each module that is not in the layout of any scan root. A script has no place in a
/// layout, so it has no gap.
fn outside(modules: &[Module], roots: &[String]) -> Vec<Record<GapFact>> {
    modules
        .iter()
        .filter(|module| !is_script(module))
        .filter(|module| !roots.iter().any(|root| in_layout(root, module)))
        .map(|module| {
            let reason = format!(
                "{OUTSIDE_LAYOUT}: the top package of module {} lies above its scan root",
                module.name
            );
            let mut gap = file_gap(&module.rel, &reason);
            // AD-564: the survey read the module; only its file and layout are not proven.
            if let GapFact::CollectionGap(data) = &mut gap.data {
                data.effect = Some(super::effects::layout(&module.name));
            }
            gap
        })
        .collect()
}

/// A gap for each linked directory below a root: Python imports its modules, the survey does not
/// read them.
fn linked(directories: &[String]) -> Vec<Record<GapFact>> {
    directories
        .iter()
        .map(|rel| file_gap(rel, &format!("{LINKED}: {rel}")))
        .collect()
}

/// A gap for each stub or compiled module file.
fn foreign(files: &[String]) -> Vec<Record<GapFact>> {
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
