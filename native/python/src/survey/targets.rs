// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The target of each import and the gaps of the import sites (AD-450).
//!
//! The first part of the target decides, as for a bare TypeScript specifier. The first part of
//! the namespace is the project: its target is a selected module, else the import is unresolved
//! and a gap names it. A standard name is builtin. Each other name is an external package.
//! A site whose edge the survey cannot know is a gap too: a star import of a project module,
//! a `from pkg import name` that can give an attribute or a module, and a relative import above
//! the top package. Each gap cites the evidence of its import, so the model finds its site.

use std::collections::{BTreeMap, HashMap, HashSet};

use archkeel_facts::envelope::{FileFact, Target};
use archkeel_facts::{GapFact, ImportFact, Record};

use super::binders::first_part;

/// The prefix of the target of a relative import that `resolve_name` refuses (`imports.rs`).
const UNRESOLVED: &str = "<unresolved:";

/// The named gaps of the import sites.
pub(super) const BEYOND_TOP: &str = "relative_import_beyond_top";
pub(super) const NOT_FOUND: &str = "project_module_not_found";
pub(super) const STAR: &str = "star_import";
pub(super) const AMBIGUOUS: &str = "reexport_ambiguity";

/// The typed targets, in the order of the imports, and the gaps of the sites, by id.
pub(super) struct Resolved {
    pub targets: Vec<Target>,
    pub gaps: BTreeMap<String, Record<GapFact>>,
}

/// A gap of one import site: the source module and the evidence of the import (AD-450).
pub(super) fn site_gap(
    kind: &str,
    detail: &str,
    module: &str,
    evidence: &str,
) -> (String, Record<GapFact>) {
    let reason = format!("{kind}: {detail}");
    let gap = GapFact::resolution(&reason, module);
    Record::unknown_gap(&reason, Some(evidence), module, gap)
}

/// `collect._import_targets` with the classification of AD-450, and the gaps of the sites.
pub(super) fn resolve(
    imports: &[Record<ImportFact>],
    files: &[FileFact],
    stdlib: &HashSet<&str>,
    namespace: &str,
    ambiguous: &HashSet<String>,
) -> Resolved {
    let by_module: HashMap<&str, &str> = files
        .iter()
        .map(|file| (file.module.as_str(), file.rel_path.as_str()))
        .collect();
    let project = first_part(namespace);
    let mut found = Resolved {
        targets: Vec::with_capacity(imports.len()),
        gaps: BTreeMap::new(),
    };
    for import in imports {
        let data = import.data.data();
        let import_id = import.id.clone();
        let module = data.target_module.as_str();
        let source = data.source_module.as_str();
        let evidence = import.evidence_ids.first().map_or("", |id| id.as_str());
        let mut gap = |kind: &str, detail: &str| {
            let (id, record) = site_gap(kind, detail, source, evidence);
            found.gaps.insert(id, record);
        };
        let symbol = data.symbol.as_deref();
        if ambiguous.contains(import.id.as_str()) {
            // The record names the package and the symbol, or the submodule (`imports.rs`).
            let name = symbol.map_or_else(|| module.to_owned(), |name| format!("{module}.{name}"));
            gap(AMBIGUOUS, &name);
        }
        let in_project = first_part(module) == project;
        if in_project && symbol == Some("*") {
            gap(STAR, module);
        }
        let unresolved = |reason: &str| Target::Unresolved {
            import_id: import_id.clone(),
            specifier: module.to_owned(),
            reason: reason.to_owned(),
        };
        let target = if module.starts_with(UNRESOLVED) {
            gap(BEYOND_TOP, module);
            unresolved("relative import above the top package")
        } else if in_project {
            match by_module.get(module) {
                Some(file) => Target::Local {
                    import_id,
                    module: data.target_module.clone(),
                    file: (*file).to_owned(),
                    runtime_file: None,
                    declaration_file: None,
                },
                None => {
                    gap(NOT_FOUND, module);
                    unresolved("module source not found")
                }
            }
        } else if stdlib.contains(first_part(module)) {
            Target::Builtin {
                import_id,
                name: module.to_owned(),
            }
        } else {
            Target::External {
                import_id,
                package: data.target_package.clone(),
            }
        };
        found.targets.push(target);
    }
    found
}

#[cfg(test)]
#[path = "targets_tests.rs"]
pub(crate) mod tests;
