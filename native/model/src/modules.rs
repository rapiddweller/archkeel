// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The modules and packages of a reply (slice S1).
//!
//! Reference engine: `check/evaluation/evaluate.py` `scan_source_facts` (the `parsed` files, `packages =
//! sorted({module.package ...})`, `module_evidence`, `blank_modules`) and the ids of
//! `check/evaluation/topology.py` `module_records`. The fan counts and ranks of the rows of the
//! `modules` and `packages` sections are in `topology.rs` (slice S3).

use std::collections::BTreeMap;

use archkeel_facts::envelope::FileFact;
use archkeel_facts::identity::{stable_id, Part};

use crate::ids::{ModuleId, PackageId, Table};
use crate::reason::Reason;

/// One module of the reply: one source file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Module {
    name: String,
    package: PackageId,
    file: String,
    evidence: String,
    blank: bool,
    fact_id: String,
    exports: Vec<String>,
    exports_literal: bool,
    compatibility_logic_free: bool,
}

impl Module {
    /// The module identity (a dotted name, or the module identity of the collector).
    pub fn name(&self) -> &str {
        &self.name
    }

    /// The package of the module.
    pub fn package(&self) -> PackageId {
        self.package
    }

    /// The repository-relative file.
    pub fn file(&self) -> &str {
        &self.file
    }

    /// The evidence id of the module (`FileFact.evidence_id`).
    pub fn evidence(&self) -> &str {
        &self.evidence
    }

    /// True when the file has no statement (the collector reads it as blank).
    pub fn blank(&self) -> bool {
        self.blank
    }

    /// The id of the module record: `stable_id("MOD", name)`.
    pub fn fact_id(&self) -> &str {
        &self.fact_id
    }

    /// The names that the module states as its exports, sorted.
    pub fn exports(&self) -> &[String] {
        &self.exports
    }

    /// True when the export list of the module is a literal.
    pub fn exports_literal(&self) -> bool {
        self.exports_literal
    }

    /// True when the collector proves that the module holds no compatibility logic.
    pub fn compatibility_logic_free(&self) -> bool {
        self.compatibility_logic_free
    }
}

/// One package of the reply: the modules that name it, in the order of the reply.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Package {
    name: String,
    modules: Vec<ModuleId>,
    fact_id: String,
}

impl Package {
    /// The dotted package name.
    pub fn name(&self) -> &str {
        &self.name
    }

    /// The modules of the package, in the order of the reply.
    pub fn modules(&self) -> &[ModuleId] {
        &self.modules
    }

    /// The id of the package record: `stable_id("PKG", name)`.
    pub fn fact_id(&self) -> &str {
        &self.fact_id
    }
}

/// The modules in the order of the reply and the packages in name order.
pub(crate) type Tables = (Table<ModuleId, Module>, Table<PackageId, Package>);

/// The modules and packages of the files of a reply.
pub(crate) fn tables(files: &[FileFact]) -> Result<Tables, Reason> {
    // The reference engine sorts the package names as `str`: by code point, as `BTreeMap` does for UTF-8.
    let mut names: BTreeMap<&str, usize> = files
        .iter()
        .map(|file| (file.package.as_str(), 0))
        .collect();
    for (index, slot) in names.values_mut().enumerate() {
        *slot = index;
    }
    let mut members: Vec<Vec<usize>> = vec![Vec::new(); names.len()];
    let mut modules = Vec::with_capacity(files.len());
    for (index, file) in files.iter().enumerate() {
        let package = names
            .get(file.package.as_str())
            .copied()
            .ok_or(Reason::TooManyRows("packages"))?;
        if let Some(slot) = members.get_mut(package) {
            slot.push(index);
        }
        modules.push((file, package));
    }
    let packages = Table::<PackageId, Package>::of_rows(
        names
            .keys()
            .zip(members)
            .map(|(name, modules)| Package {
                name: (*name).to_owned(),
                modules: modules.into_iter().map(module_id).collect(),
                fact_id: stable_id("PKG", &[Part::Text(name)]),
            })
            .collect(),
    )
    .ok_or(Reason::TooManyRows("packages"))?;
    let modules = Table::<ModuleId, Module>::of_rows(
        modules
            .into_iter()
            .map(|(file, package)| Module {
                name: file.module.as_str().to_owned(),
                package: package_id(package),
                file: file.rel_path.clone(),
                evidence: file.evidence_id.as_str().to_owned(),
                blank: file.blank,
                fact_id: stable_id("MOD", &[Part::Text(file.module.as_str())]),
                exports: sorted(&file.all_exports),
                exports_literal: file.all_literal,
                compatibility_logic_free: file.compatibility_logic_free,
            })
            .collect(),
    )
    .ok_or(Reason::TooManyRows("modules"))?;
    Ok((modules, packages))
}

fn sorted(names: &[String]) -> Vec<String> {
    let mut names = names.to_vec();
    names.sort();
    names
}

/// The id of a row index that `Table::of_rows` checked.
fn module_id(index: usize) -> ModuleId {
    crate::ids::id_of(index)
}

fn package_id(index: usize) -> PackageId {
    crate::ids::id_of(index)
}
