// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The edges of one module to other crates: the import record of each path that names another
//! crate, the UNKNOWN record of a name that the scan cannot place, and the safety net.

use std::collections::BTreeSet;

use archkeel_facts::data::ImportData;
use archkeel_facts::envelope::{Evidence, Target};
use archkeel_facts::identity::{package_of, stable_id, Part};
use archkeel_facts::ids::{FactId, ModuleName, PackageName};
use archkeel_facts::{ImportFact, Record};

use crate::builder::{import_record, Builder, Origin};
use crate::crates::{Crate, Root, Workspace};
use crate::derive_imports::Local;
use crate::modules::{Index, Outcome};
use crate::names::{self, glob_of, published, with_name, ImportName};
use crate::registry_overrides::Cited;
use crate::resolve::{classify, linked, Found, Named};
use crate::scan::{Reference, Via};
use crate::site::Site;
use crate::tree::Module;

impl Builder {
    pub(crate) fn module(
        &mut self,
        workspace: &Workspace,
        index: &Index<'_>,
        module: &Module,
        modules: &[Module],
    ) {
        let first = module.first_line.as_str();
        let (line, column) = if first.is_empty() { (0, 0) } else { (1, 0) };
        let cited = Evidence::at(&module.rel, line, line, column, first);
        self.file(
            (&module.rel, &module.module, module.package()),
            module.blank,
            cited,
        );
        self.edges(workspace, index, module);
        self.symbols(module);
        let local = Local::of(module);
        for concern in &module.scan.concerns {
            if crate::derive_identity::proven(workspace, index, &local, concern, modules) {
                continue;
            }
            if let Some(found) = crate::derive_identity::withheld(workspace, &local, concern) {
                self.withheld(module, found);
            }
            let evidence = self.cite(&module.rel, &concern.site);
            if let Some(scope) = &concern.source {
                let source = std::iter::once(module.module.as_str())
                    .chain(scope.iter().map(String::as_str))
                    .collect::<Vec<_>>()
                    .join(".");
                self.pair_gap(&concern.reason, &evidence, (&source, ""), false);
            } else {
                self.gap(&concern.reason, Some(&evidence), &module.module);
            }
        }
    }

    /// A modeled registry derive whose crate a setting of the repository may build from other
    /// code (AD-774): a gap of the module that names the setting, its file and its line.
    fn withheld(&mut self, module: &Module, (package, cited): (&str, &Cited)) {
        let at = match cited.line {
            0 => cited.rel.clone(),
            line => format!("{}:{line}", cited.rel),
        };
        let reason = format!(
            "{} in {at} may build the registry crate {package} from other code than Cargo.lock records: its derive has no identity proof",
            cited.what
        );
        let site = Site {
            line: cited.line,
            end_line: cited.line,
            column: 0,
            excerpt: cited.excerpt.clone(),
        };
        let evidence = (cited.line > 0).then(|| self.cite(&cited.rel, &site));
        self.gap(&reason, evidence.as_deref(), &module.module);
    }

    fn edges(&mut self, workspace: &Workspace, index: &Index<'_>, module: &Module) {
        let Some(krate) = workspace.crates.get(module.crate_index) else {
            return;
        };
        let mut covered = BTreeSet::new();
        let before = self.ended;
        #[cfg(feature = "dump")]
        let references = module.scan.references.iter().enumerate();
        #[cfg(not(feature = "dump"))]
        let references = module
            .scan
            .references
            .iter()
            .map(|reference| (0, reference));
        for (_at, reference) in references {
            #[cfg(feature = "dump")]
            if std::env::var("ARCHKEEL_PLANT_SKIP")
                .is_ok_and(|value| value == format!("{}:{_at}", module.rel))
            {
                continue;
            }
            // An alias of `extern crate self` beats a dependency and a name of the sysroot.
            let alias = index.is_alias(&module.module, &reference.root);
            let found = classify(
                &reference.root,
                krate,
                &module.scan.shadows,
                reference.absolute,
            )
            .filter(|_| !alias);
            if found.is_some() || alias {
                covered.insert(reference.root.clone());
            }
            match found {
                #[cfg(feature = "dump")]
                Some(Found::Edge(_))
                    if std::env::var("ARCHKEEL_PLANT_ARM")
                        .is_ok_and(|value| value == format!("{}:{_at}", module.rel)) => {}
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
                    self.ended += 1;
                }
                None => match bound_crate_path(index, workspace, krate, module, reference) {
                    Some((full, named)) => {
                        self.import(workspace, Some(index), Origin::of(module), &full, &named);
                    }
                    None => self.module_edge(index, module, reference),
                },
            }
        }
        let ended = self.ended - before;
        self.ended_references.insert(module.rel.clone(), ended);
        self.net(krate, module, &covered);
        for (name, site) in &module.scan.extern_crates {
            if !linked(name, krate) {
                // Only a link that a `build.rs` prints gives this crate: the collector does not read it.
                let reason = format!("The manifest does not declare the extern crate {name}");
                let evidence = self.cite(&module.rel, site);
                self.gap(&reason, Some(&evidence), &module.module);
            }
        }
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
        let (target_module, mut key) = match named {
            Named::Sysroot(name) => (name.clone(), format!("sysroot:{name}")),
            Named::Package(package) | Named::Registry(package) => {
                (package.clone(), format!("package:{package}"))
            }
        };
        // A template cannot supply evidence for a path in ordinary code.
        if reference.in_macro.is_some() {
            key.insert_str(0, "template:");
        }
        // One record for each distinct path of a file; the first use is its evidence.
        if !self
            .seen
            .insert((from.module.to_owned(), key, reference.path.clone()))
        {
            self.ended += 1;
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
        let import_id = FactId::new(identity.as_str());
        // AD-622: a crate never names itself as a dependency, so a workspace root of
        // `Named::Package` is another crate.
        let mut other_crate = false;
        let (target, target_module, name) = match named {
            Named::Sysroot(name) => (
                Target::Builtin {
                    import_id,
                    name: name.clone(),
                },
                target_module,
                None,
            ),
            Named::Registry(package) => {
                // #946: a registry dependency can redirect to a same-named workspace crate.
                if let Some(root) = workspace.primary_of(package) {
                    let id = FactId::new(identity.as_str());
                    let local = local_target(index, root, reference, id)
                        .map_or_else(|_| root.module.clone(), |(_, module, _)| module);
                    let reason = format!(
                        "The dependency {package} has a registry or git entry, and a crate of the workspace has its name: a redirect that the scan does not read can make it that crate"
                    );
                    self.pair_gap(&reason, &evidence, (from.module, &local), false);
                }
                (
                    Target::External {
                        import_id,
                        package: PackageName::new(package.as_str()),
                    },
                    target_module,
                    None,
                )
            }
            Named::Package(package) => match workspace.primary_of(package) {
                Some(root) => {
                    other_crate = true;
                    let found = local_target(index, root, reference, import_id);
                    // #1405: a path into the workspace that the index cannot read is UNKNOWN,
                    // as the same path inside one crate is (`module_edges::unreadable`).
                    let (target, module, name) = match found {
                        Ok(found) => found,
                        Err(reason) => {
                            self.gap(&reason, Some(&evidence), from.module);
                            self.ended += 1;
                            return;
                        }
                    };
                    let glob = matches!(reference.via, crate::scan::Via::Glob { .. });
                    (
                        target,
                        module,
                        Some(if glob { glob_of(name) } else { name }),
                    )
                }
                None => (
                    Target::External {
                        import_id,
                        package: PackageName::new(package.as_str()),
                    },
                    target_module,
                    None,
                ),
            },
        };
        self.push_import(
            from,
            reference,
            &identity,
            evidence,
            index,
            (target, target_module, name, other_crate),
        );
    }

    /// Adds the import record of a resolved path: its target, its item (AD-604) and its published name.
    fn push_import(
        &mut self,
        from: Origin<'_>,
        reference: &Reference,
        identity: &str,
        evidence: String,
        index: Option<&Index<'_>>,
        (target, target_module, name, other_crate): (Target, String, Option<ImportName>, bool),
    ) {
        let external = name.as_ref().and_then(ImportName::external_package);
        if let Some(package) = external.filter(|_| reference.in_macro.is_none()) {
            self.external_origin(from.module, &evidence, package);
        }
        let record = record(
            index,
            from.module,
            reference,
            (identity, evidence),
            (&target_module, &target),
        );
        self.targets.push(target);
        // AD-604: an import into the workspace names its item; an external one is not read.
        let mut record = match name {
            Some(name) => with_name(record, name),
            None => record,
        };
        record.data.data_mut().published_as =
            index.and_then(|index| published(index, from.module, reference));
        record.data.data_mut().other_crate = other_crate.then_some(true);
        self.imports.push(record);
        self.ended += 1;
    }
}

/// A path that names another crate of the workspace through a `use` leaf of its file
/// (`use dep::m; m::f()`), as the path from that crate and its crate. Without its own record, the
/// interface rule would not see the name that such a path uses (AD-604).
fn bound_crate_path(
    index: &Index<'_>,
    workspace: &Workspace,
    krate: &Crate,
    module: &Module,
    reference: &Reference,
) -> Option<(Reference, Named)> {
    if reference.in_macro.is_some() || reference.names.len() < 2 {
        return None;
    }
    let names = index.crate_path(index.frame(&module.module)?, reference)?;
    match classify(&names[0], krate, &module.scan.shadows, false)? {
        // #946: a registry name of a crate of the workspace may be that crate.
        Found::Edge(named @ (Named::Package(_) | Named::Registry(_))) if !matches!(&named, Named::Registry(p) if workspace.primary_of(p).is_none()) =>
        {
            let full = Reference {
                root: names[0].clone(),
                names,
                via: crate::scan::Via::Path,
                ..reference.clone()
            };
            Some((full, named))
        }
        // A path into a crate outside the workspace is no crossing of a component.
        _ => None,
    }
}

/// The import record of one path that names another crate.
fn record(
    index: Option<&Index<'_>>,
    module: &str,
    reference: &Reference,
    (identity, evidence): (&str, String),
    (target_module, target): (&str, &Target),
) -> Record<ImportFact> {
    let source_package = index
        .and_then(|index| index.frame(module))
        .map_or_else(|| package_of(module), |frame| frame.module.package());
    let target_package = match target {
        Target::Local { module, .. } => index
            .and_then(|index| index.frame(module.as_str()))
            .map_or(module.as_str(), |frame| frame.module.package()),
        _ => target_module,
    };
    let data = ImportData {
        source_module: ModuleName::new(module),
        source_package: PackageName::new(source_package),
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

/// The target of a path into another crate of the workspace: the deepest module that the path
/// names below the root of that crate. Without an index (a declared dependency) it is the root.
/// The name is the item after that module and its route (AD-604); a declared dependency names the
/// whole crate. A path that the index cannot read is an error with its reason (#1405): a whole
/// crate with no name would let a rule on one of its items pass.
pub(crate) fn local_target(
    index: Option<&Index<'_>>,
    root: &Root,
    reference: &Reference,
    import_id: FactId,
) -> Result<(Target, String, ImportName), String> {
    let rest = reference.names.get(1..).unwrap_or(&[]);
    let deepest = match index {
        None => None,
        Some(index) => match index.reach(&root.module, rest) {
            Outcome::Edge(edge) if !matches!(reference.via, Via::Glob { .. }) => {
                if let Some(reason) = index.module_or_item(&edge) {
                    return Err(reason);
                }
                index.rel(&edge.module).map(|rel| {
                    let named = names::item(index, &edge.lexical, edge.symbol.as_deref());
                    (edge.module.clone(), rel.to_owned(), named)
                })
            }
            Outcome::Edge(edge) => index.rel(&edge.module).map(|rel| {
                let named = names::item(index, &edge.lexical, edge.symbol.as_deref());
                (edge.module.clone(), rel.to_owned(), named)
            }),
            Outcome::Unknown(reason) => return Err(reason),
            Outcome::None => None,
        },
    };
    let whole = ImportName::whole();
    let (module, file, named) =
        deepest.unwrap_or_else(|| (root.module.clone(), root.rel.clone(), whole));
    let target = Target::Local {
        import_id,
        module: ModuleName::new(module.as_str()),
        file: file.clone(),
        runtime_file: Some(file),
        declaration_file: None,
    };
    Ok((target, module, named))
}
