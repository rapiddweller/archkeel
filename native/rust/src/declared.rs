// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The edges that a fact other than the source syntax gives. The manifests declare dependencies: source
//! can hide a use (a macro, a generated token), but it cannot use a crate that the manifest does not declare.
//! The compiler selects impls: a call of `PartialEq::eq` runs the impl of another module (AD-1129).

use std::collections::BTreeSet;

use archkeel_facts::data::ImportData;
use archkeel_facts::envelope::{Evidence, Target};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{FactId, ModuleName, PackageName};
use archkeel_facts::ImportFact;
use archkeel_snapshot::paths::join;
use archkeel_snapshot::Snapshot;

use crate::builder::{import_record, Builder, Form, Origin};
use crate::crates::{Crate, Workspace};
use crate::manifest::Kind;
use crate::modules::Index;
use crate::resolve::Named;
use crate::scan::{Reference, Site};
use crate::tree::Module;
use crate::type_reach_filter::Filter;

impl Builder {
    /// A dependency that a manifest declares is an edge of its crate, in the section that it is
    /// declared in. Source can hide a use (a macro, a generated token), but it cannot use a crate
    /// that the manifest does not declare. The edge starts in the main module of the crate; the
    /// kind of the section is in the text of the specifier, until module scope exists (5b-2).
    pub(crate) fn declare_dependencies(
        &mut self,
        workspace: &Workspace,
        namespace: &str,
        taken: &BTreeSet<&str>,
        source: &mut Snapshot,
    ) {
        for krate in &workspace.crates {
            let rel = join(&krate.dir, "Cargo.toml");
            let text = krate.text.as_str();
            source.select(&rel);
            let mut module = format!("{namespace}.{}.cargo_toml", krate.ident);
            while taken.contains(module.as_str()) {
                module.push('_');
            }
            let first = text.lines().next().unwrap_or("").trim_end();
            let cited = Evidence::at(&rel, 1, 1, 0, first);
            self.file(
                (&rel, &module, archkeel_facts::identity::package_of(&module)),
                text.trim().is_empty(),
                cited,
            );
            self.manifests.push(rel.clone());
            self.declared_edges(workspace, krate, &module);
        }
    }

    /// The edge of each dependency that the manifest of `krate` declares.
    fn declared_edges(&mut self, workspace: &Workspace, krate: &Crate, module: &str) {
        let rel = join(&krate.dir, "Cargo.toml");
        let exclude = self.exclude_tests;
        let others = krate
            .manifest
            .declared
            .iter()
            .filter(|dependency| dependency.package != krate.ident)
            .filter(|dependency| !(exclude && dependency.kind == Kind::Dev));
        for dependency in others {
            let (line, excerpt) = krate.lines.find(dependency.kind, &dependency.key);
            let reference = Reference {
                root: dependency.package.clone(),
                path: format!("{}: {}", dependency.kind.section(), dependency.key),
                site: Site {
                    line,
                    end_line: line,
                    column: 0,
                    excerpt,
                },
                absolute: true,
                ..Reference::default()
            };
            let from = Origin {
                module,
                rel: &rel,
                form: Form::Declared,
            };
            let package = dependency.package.clone();
            let named = if krate.manifest.remote.contains(&package) {
                Named::Registry(package)
            } else {
                Named::Package(package)
            };
            self.import(workspace, None, from, &reference, &named);
        }
    }

    /// One `selected_impl` import for each call that the compiler resolved to the impl of another scan module.
    /// The call is the evidence. The record names no symbol: the compiler gives the module of the impl.
    /// The edge comes after the gaps are settled and no gap leaves for it: a site that the compiler did not
    /// resolve stays a gap (AD-806, AD-1129).
    pub(crate) fn selected_edges(
        &mut self,
        index: &Index<'_>,
        modules: &[Module],
        reach: Option<&Filter<'_>>,
    ) {
        for found in reach.map(Filter::selected).unwrap_or_default() {
            let source = modules.iter().find(|m| m.module == found.from);
            // The store requires the evidence file to be the file of the source module. A call in another
            // file (an `include!`, a `#[path]` module) has no such evidence: it stays a gap.
            let Some(from) = source.filter(|m| m.rel == found.file) else {
                continue;
            };
            let Some(target_rel) = index.rel(&found.to) else {
                continue;
            };
            let target_package = index.frame(&found.to).map_or("", |f| f.module.package());
            let site = Site {
                line: found.line,
                end_line: found.line,
                column: found.column,
                excerpt: format!("the compiler selected {}", found.imp),
            };
            let identity = stable_id(
                "SEL",
                &[
                    Part::Text(&found.from),
                    Part::Number(found.line),
                    Part::Number(found.column),
                    Part::Text(&found.to),
                    Part::Text(&found.imp),
                ],
            );
            let evidence = self.cite(&found.file, &site);
            self.targets.push(Target::Local {
                import_id: FactId::new(identity.as_str()),
                module: ModuleName::new(found.to.as_str()),
                file: target_rel.to_owned(),
                runtime_file: Some(target_rel.to_owned()),
                declaration_file: None,
            });
            let data = ImportData {
                source_module: ModuleName::new(&found.from),
                source_package: PackageName::new(from.package()),
                target_module: ModuleName::new(&found.to),
                target_package: PackageName::new(target_package),
                specifier: Some(found.imp.clone()),
                ..ImportData::statement()
            };
            let subjects = vec![found.from.clone(), found.to.clone()];
            let at = (found.from.as_str(), found.imp.as_str());
            let fact = ImportFact::SelectedImpl(data);
            self.imports
                .push(import_record((&identity, evidence), at, subjects, fact));
        }
    }
}
