// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The edges that the manifests declare. Source can hide a use (a macro, a generated token), but
//! it cannot use a crate that the manifest does not declare.

use std::collections::BTreeSet;

use archkeel_snapshot::paths::join;
use archkeel_snapshot::Snapshot;
use archkeel_wire::reply::Evidence;

use crate::builder::{Builder, Form, Origin};
use crate::crates::{Crate, Workspace};
use crate::manifest::Kind;
use crate::resolve::Named;
use crate::scan::{Reference, Site};

impl Builder {
    /// A dependency that a manifest declares is an edge of its crate, in the section that it is
    /// declared in. Source can hide a use (a macro, a generated token), but it cannot use a crate
    /// that the manifest does not declare. The edge starts in the main module of the crate; the
    /// kind of the section is in the text of the specifier, until module scope exists (5b-2).
    pub(crate) fn declared(
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
            self.file((&rel, &module), text.trim().is_empty(), cited);
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
            let named = Named::Package(dependency.package.clone());
            self.import(workspace, None, from, &reference, &named);
        }
    }
}
