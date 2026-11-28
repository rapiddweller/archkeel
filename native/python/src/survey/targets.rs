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

use archkeel_facts::data::GapData;
use archkeel_facts::envelope::{FileFact, Target};
use archkeel_facts::vocab::ResolutionDimension;
use archkeel_facts::{GapFact, ImportFact, Record};

use super::binders::first_part;
use super::effects::{self, AMBIGUOUS, AMBIGUOUS_ROOTS, BEYOND_TOP, NOT_FOUND, STAR};
use crate::names::importable_path;

/// The prefix of the target of a relative import that `resolve_name` refuses (`imports.rs`).
const UNRESOLVED: &str = "<unresolved:";

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
    let mut data = GapData::at(&reason, module);
    data.resolution_dimension = Some(ResolutionDimension::Imports);
    // AD-564: what the site leaves unknown. The id of the record does not read it.
    data.effect = effects::of(kind, module);
    let gap = GapFact::SourceResolutionGap(data);
    Record::unknown_gap(&reason, Some(evidence), module, gap)
}

/// The gap of a hazard site of `module` with the evidence `id`. Each site states its name, its
/// line, its scope and the name that it binds, so a contract can declare its reach by name
/// (AD-664, AD-1052). A site of a trojan horse form states the form too. `exposed` lists the modules
/// that can reach the bound name. The id of the gap does not read the trojan horse.
pub(super) fn hazard_gap(
    site: super::hazards::Site,
    module: &crate::module::Module,
    (id, exposed): (&str, Vec<String>),
) -> (String, Record<GapFact>) {
    let (key, mut gap) = site_gap(site.kind, &site.detail, &module.name, id);
    if let GapFact::SourceResolutionGap(data) = &mut gap.data {
        data.namespace = site.namespace;
        data.trojan_horse = Some(archkeel_facts::data::TrojanHorseSite {
            form: site.trojan_horse,
            site_name: Some(site.detail),
            line: u32::try_from(module.location(&site.range).line).unwrap_or(0),
            line_only: false,
            scope: Some(site.scope).filter(|scope| !scope.is_empty()),
            binding: site.binding,
            exposed_to: exposed,
        });
    }
    (key, gap)
}

/// The trojan horse of a site that has a name and no line: it lies at the module level.
fn unlocated(name: &str) -> archkeel_facts::data::TrojanHorseSite {
    archkeel_facts::data::TrojanHorseSite {
        form: None,
        site_name: Some(name.to_owned()),
        line: 0,
        line_only: false,
        scope: Some(String::new()),
        binding: None,
        exposed_to: Vec::new(),
    }
}

/// `collect._import_targets` with the classification of AD-450, and the gaps of the sites.
pub(super) fn resolve(
    imports: &[Record<ImportFact>],
    files: &[FileFact],
    stdlib: &HashSet<&str>,
    (project, root_relative, uncertain): (&HashSet<String>, bool, bool),
    ambiguous: &HashSet<String>,
) -> Resolved {
    let by_module: HashMap<&str, &str> = files
        .iter()
        .filter(|file| {
            !root_relative || importable_path(String::as_str(&file.rel_path), file.module.as_str())
        })
        .map(|file| (file.module.as_str(), String::as_str(&file.rel_path)))
        .collect();
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
            let (id, mut record) = site_gap(kind, detail, source, evidence);
            if let (AMBIGUOUS, GapFact::SourceResolutionGap(data)) = (kind, &mut record.data) {
                // No line: the name of the submodule is the key of the site (AD-1052).
                data.trojan_horse = Some(unlocated(detail));
            }
            found.gaps.insert(id, record);
        };
        let symbol = data.symbol.as_deref();
        if ambiguous.contains(import.id.as_str()) {
            // The record names the package and the symbol, or the submodule (`imports.rs`).
            let name = symbol.map_or_else(|| module.to_owned(), |name| format!("{module}.{name}"));
            gap(AMBIGUOUS, &name);
        }
        let in_project = project.contains(first_part(module));
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
        } else if uncertain && (in_project || !stdlib.contains(first_part(module))) {
            gap(AMBIGUOUS_ROOTS, module);
            unresolved("runtime Python import roots are ambiguous")
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
