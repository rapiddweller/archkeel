// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The edges of one module to other crates: the import record of each path that names another
//! crate, the UNKNOWN record of a name that the scan cannot place, and the safety net.

use std::collections::BTreeSet;

use archkeel_facts::data::ImportData;
use archkeel_facts::identity::{package_of, stable_id, Part};
use archkeel_facts::ids::{ModuleName, PackageName};
use archkeel_facts::reply::{Evidence, Target};
use archkeel_facts::{ImportFact, Record};

use crate::builder::{import_record, Builder, Origin};
use crate::crates::{Crate, Workspace};
use crate::module_edges::local_target;
use crate::modules::Index;
use crate::resolve::{classify, Found, Named};
use crate::scan::Reference;
use crate::tree::Module;

impl Builder {
    pub(crate) fn module(&mut self, workspace: &Workspace, index: &Index<'_>, module: &Module) {
        let first = module.first_line.as_str();
        let (line, column) = if first.is_empty() { (0, 0) } else { (1, 0) };
        let cited = Evidence::at(&module.rel, line, line, column, first);
        self.file((&module.rel, &module.module), module.blank, cited);
        self.edges(workspace, index, module);
        for concern in &module.scan.concerns {
            let evidence = self.cite(&module.rel, &concern.site);
            self.gap(&concern.reason, Some(&evidence), &module.module);
        }
    }

    fn edges(&mut self, workspace: &Workspace, index: &Index<'_>, module: &Module) {
        let Some(krate) = workspace.crates.get(module.crate_index) else {
            return;
        };
        let mut covered = BTreeSet::new();
        for reference in &module.scan.references {
            let found = classify(
                &reference.root,
                krate,
                &module.scan.shadows,
                reference.absolute,
            );
            if found.is_some() {
                covered.insert(reference.root.clone());
            }
            match found {
                Some(Found::Edge(named)) => {
                    self.import(
                        workspace,
                        Some(index),
                        Origin::of(module),
                        reference,
                        &named,
                    );
                }
                Some(Found::Shadowed) => {
                    let reason = format!("A local name equals a crate name: {}", reference.root);
                    let evidence = self.cite(&module.rel, &reference.site);
                    self.gap(&reason, Some(&evidence), &module.module);
                }
                None => self.module_edge(index, module, reference),
            }
        }
        self.net(krate, module, &covered);
    }

    /// The safety net: a reachable crate name that the file writes, and that no edge explains.
    fn net(&mut self, krate: &Crate, module: &Module, covered: &BTreeSet<String>) {
        let none = BTreeSet::new();
        for name in &module.scan.mentioned {
            if covered.contains(name) || classify(name, krate, &none, false).is_none() {
                continue;
            }
            let reason =
                format!("The crate name {name} appears in a place the collector does not read");
            self.gap(&reason, None, &module.module);
        }
    }

    pub(crate) fn import(
        &mut self,
        workspace: &Workspace,
        index: Option<&Index<'_>>,
        from: Origin<'_>,
        reference: &Reference,
        named: &Named,
    ) {
        let (target_module, key) = match named {
            Named::Sysroot(name) => (name.clone(), format!("sysroot:{name}")),
            Named::Package(package) => (package.clone(), format!("package:{package}")),
        };
        // One record for each distinct path of a file; the first use is its evidence.
        if !self
            .seen
            .insert((from.module.to_owned(), key, reference.path.clone()))
        {
            return;
        }
        let site = &reference.site;
        let identity = stable_id(
            "IMP",
            &[
                Part::Text(from.module),
                Part::Number(site.line),
                Part::Number(site.column),
                Part::Text(from.form.text()),
            ],
        );
        let evidence = self.cite(from.rel, site);
        let import_id = identity.clone();
        let (target, target_module) = match named {
            Named::Sysroot(name) => (
                Target::Builtin {
                    import_id,
                    name: name.clone(),
                },
                target_module,
            ),
            Named::Package(package) => match workspace.primary_of(package) {
                Some(root) => local_target(index, root, reference, import_id),
                None => (
                    Target::External {
                        import_id,
                        package: package.clone(),
                    },
                    target_module,
                ),
            },
        };
        let target_package = match &target {
            Target::Local { module, .. } => package_of(module).to_owned(),
            _ => target_module.clone(),
        };
        self.targets.push(target);
        self.imports.push(record(
            from.module,
            reference,
            &identity,
            evidence,
            &target_module,
            &target_package,
        ));
    }
}

/// The import record of one path that names another crate.
fn record(
    module: &str,
    reference: &Reference,
    identity: &str,
    evidence: String,
    target_module: &str,
    target_package: &str,
) -> Record<ImportFact> {
    let data = ImportData {
        source_module: ModuleName::new(module),
        source_package: PackageName::new(package_of(module)),
        target_module: ModuleName::new(target_module),
        target_package: PackageName::new(target_package),
        specifier: Some(reference.path.clone()),
        module_level_import: true,
        ..ImportData::statement()
    };
    let subjects = vec![module.to_owned(), target_module.to_owned()];
    let at = (module, reference.path.as_str());
    import_record((identity, evidence), at, subjects, ImportFact::Import(data))
}
