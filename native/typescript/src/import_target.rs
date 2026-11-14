// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The target of one import reference: a builtin, a package, a local file or an unresolved name
//! (`collect._target` and below). The specifier and its class are read once, in `Ref`, and every
//! step takes that `Ref`; the record of the import is built in `imports.rs`.

use archkeel_facts::envelope::Target;
use archkeel_facts::identity::module_identity;
use archkeel_facts::ids::{FactId, ModuleName, PackageName};
use archkeel_snapshot::paths::{dirname, join, within};

use super::{Collection, GapKind};
use crate::installed::{in_node_modules, installed};
use crate::manifest::Lookup;
use crate::references::{Form, Reference};
use crate::resolve::Found;
use crate::source_input::{
    classify_asset, classify_file, ModuleFormat, SourceKind, Specifier, SpecifierKind,
};

// The reserved identity of an asset edge; a colon cannot occur in an npm package name.
const BUNDLER_ASSET: &str = "bundler:asset";

/// Where an import was written: its evidence id and its module.
type Site = (String, String);

/// One reference as the steps of its target read it: the specifier is classified once.
pub(super) struct Ref<'r> {
    pub rel: &'r str,
    pub module: &'r str,
    pub reference: &'r Reference,
    pub specifier: &'r str,
    pub class: Specifier,
    pub identity: &'r str,
    /// The evidence id of the reference, cited once by the caller.
    pub evidence: &'r str,
}

impl Ref<'_> {
    fn import_id(&self) -> FactId {
        FactId::new(self.identity)
    }
}

impl Collection<'_> {
    /// `collect._selected`: a source file in scope that is not installed and not a test source.
    fn selected(&mut self, rel: &str) -> bool {
        !installed(&mut self.snapshot, rel)
            && self.roots.iter().any(|root| within(root, rel))
            && !self.excluded_test(rel)
    }

    fn unresolved(&mut self, r: &Ref, reason: &str) -> Target {
        self.gap(reason, None, r.module, GapKind::Resolution);
        Target::Unresolved {
            import_id: r.import_id(),
            specifier: r.specifier.to_owned(),
            reason: reason.to_owned(),
        }
    }

    pub(super) fn target(&mut self, r: &Ref, format: &Lookup<ModuleFormat>) -> Target {
        let (reference, specifier, source) = (r.reference, r.specifier, &r.class);
        let import_id = r.import_id();
        if !reference.type_only && source.kind == SpecifierKind::Node && source.builtin() {
            return Target::Builtin {
                import_id,
                name: specifier.to_owned(),
            };
        }
        if reference.mode_override {
            let reason = format!("Resolution mode override is not observed: {specifier}");
            return self.unresolved(r, &reason);
        }
        if let Some(blocked) = self.resolver.blocked.clone() {
            return self.unresolved(r, &blocked.reason);
        }
        let known = !matches!(format, Lookup::Missing);
        let mode = match format {
            Lookup::Unknown(unknown) => {
                return self.unresolved(r, &unknown.reason);
            }
            Lookup::Hit(format) => Some(*format),
            Lookup::Missing => None,
        };
        let mode = match reference.form {
            Form::DynamicImport => known.then_some(ModuleFormat::Esm),
            Form::Require | Form::ImportEquals => known.then_some(ModuleFormat::Cjs),
            _ => mode,
        };
        let prefer_builtin = !reference.type_only;
        let found = self.resolver.resolve_classified(
            &mut self.snapshot,
            (specifier, source),
            r.rel,
            mode,
            prefer_builtin,
        );
        match found {
            Lookup::Unknown(unknown) => {
                if self.bundler && unknown.package_internal && source.npm_package() {
                    // The bundler picks the file inside the package; the package is the dependency.
                    return Target::External {
                        import_id,
                        package: PackageName::new(source.package.clone()),
                    };
                }
                self.unresolved(r, &unknown.reason)
            }
            Lookup::Missing => {
                if source.builtin() {
                    return Target::Builtin {
                        import_id,
                        name: specifier.to_owned(),
                    };
                }
                if let Some(asset) = self.bundler.then(|| self.bundler_asset(r)).flatten() {
                    return asset;
                }
                let reason = format!("Unresolved module: {specifier}");
                self.unresolved(r, &reason)
            }
            Lookup::Hit(found) => self.local(r, &found),
        }
    }

    /// An existing asset that a bundler loads itself; a missing one stays an unresolved module.
    fn bundler_asset(&mut self, r: &Ref) -> Option<Target> {
        let (rel, source) = (r.rel, &r.class);
        let path = classify_asset(r.specifier)?;
        let import_id = r.import_id();
        let asset = || Target::External {
            import_id: r.import_id(),
            package: PackageName::new(BUNDLER_ASSET),
        };
        if source.relative_path() && self.resolver.file_exists(&mut self.snapshot, rel, path) {
            return Some(asset());
        }
        if !source.relative() && self.resolver.alias_file_exists(&mut self.snapshot, path) {
            return Some(asset());
        }
        if source.npm_package()
            && self
                .resolver
                .package_file_exists(&mut self.snapshot, rel, path)
        {
            return Some(Target::External {
                import_id,
                package: PackageName::new(source.package.clone()),
            });
        }
        None
    }

    /// `collect._observe`: read a local dependency; it joins the walk when it is a source file.
    fn observe(&mut self, rel: &str, importer: &Site) -> bool {
        let present = self.snapshot.readable(rel);
        let source = classify_file(rel).and_then(|suffix| suffix.source_kind());
        if present && source.is_some() && self.selected(rel) {
            if self.queued.insert(rel.to_owned()) {
                self.queue.push(rel.to_owned());
            }
        } else if present && self.excluded_test(rel) {
            let reason = format!("Production import targets excluded test source: {rel}");
            self.gap(&reason, Some(&importer.0), &importer.1, GapKind::Resolution);
        } else if present {
            let reason = format!("Local dependency outside selected source scope: {rel}");
            self.gap(&reason, None, "", GapKind::Resolution);
        }
        present
    }

    fn excluded_test_target(&mut self, r: &Ref, path: &str, site: &Site) -> Target {
        if !self.observe(path, site) {
            let reason = format!("Excluded test source is unavailable: {path}");
            return self.unresolved(r, &reason);
        }
        Target::Unresolved {
            import_id: r.import_id(),
            specifier: r.specifier.to_owned(),
            reason: format!("Excluded test source: {path}"),
        }
    }

    #[expect(
        clippy::cognitive_complexity,
        reason = "the function is over 15 in cognitive complexity: simplify it (AD-327)"
    )]
    #[expect(
        clippy::excessive_nesting,
        reason = "the function nests blocks deeper than 4: flatten it (AD-327)"
    )]
    #[expect(
        clippy::too_many_lines,
        reason = "the function is over 100 lines: split it at a seam (AD-327)"
    )]
    fn local(&mut self, r: &Ref, found: &Found) -> Target {
        let (rel, module, reference) = (r.rel, r.module, r.reference);
        let (specifier, source) = (r.specifier, &r.class);
        let path = found.path.clone();
        // AD-488: a file that the import reaches other than by a `node_modules` search makes its
        // installed package project source.
        if !found.external {
            self.reach.insert(path.clone());
        }
        let suffix = classify_file(&path);
        let site: Site = (r.evidence.to_owned(), module.to_owned());
        if self.excluded_test(&path) && !installed(&mut self.snapshot, &path) {
            return self.excluded_test_target(r, &path, &site);
        }
        if !self.snapshot.readable(&path) {
            let reason = format!("Unavailable local target: {specifier}");
            return self.unresolved(r, &reason);
        }
        let installed = in_node_modules(&path);
        if installed || (!self.selected(&path) && found.external) {
            let reason = if source.kind == SpecifierKind::Imports {
                format!("External package alias identity is not observed: {specifier}")
            } else if source.relative() {
                format!("Unidentified external package: {specifier}")
            } else {
                let import_id = r.import_id();
                return Target::External {
                    import_id,
                    package: PackageName::new(source.package.clone()),
                };
            };
            return self.unresolved(r, &reason);
        }
        let in_source = suffix.is_some_and(|suffix| suffix.source_kind().is_some());
        if self.bundler && !(self.selected(&path) && in_source) {
            let import_id = r.import_id();
            if classify_asset(&path).is_some() {
                return Target::External {
                    import_id,
                    package: PackageName::new(BUNDLER_ASSET),
                };
            }
            if found.via_paths && !source.relative() && source.npm_package() {
                // A workspace alias outside the scan roots is a dependency on that package.
                return Target::External {
                    import_id,
                    package: PackageName::new(source.package.clone()),
                };
            }
        }
        let type_only = reference.type_only;
        let relative = source.relative_path();
        let lookup = join(
            match dirname(rel) {
                "" => ".",
                directory => directory,
            },
            specifier,
        );
        let declaration = suffix
            .is_some_and(|suffix| suffix.source_kind() == Some(SourceKind::Declaration))
            .then(|| path.clone());
        let mut runtime = if declaration.is_some() {
            None
        } else {
            Some(path.clone())
        };
        let explicit =
            relative && classify_file(specifier).is_some_and(|suffix| suffix.explicit_runtime());
        let direct = matches!(reference.form, Form::Require | Form::ImportEquals);
        let common_lookup = relative && direct && !explicit;
        if !type_only {
            // Compiler substitution does not prove the file that Node loads.
            if explicit && self.snapshot.is_file(&lookup) {
                let real = self.snapshot.real(&lookup).unwrap_or(lookup);
                if self.observe(&real, &site) {
                    runtime = Some(real);
                }
            } else if declaration.is_some() || (explicit && direct) {
                runtime = None;
                let reason = if declaration.is_some() {
                    format!("Runtime implementation unavailable for declaration: {path}")
                } else {
                    format!("CommonJS runtime file is unavailable: {specifier}")
                };
                self.gap(&reason, None, "", GapKind::Resolution);
            }
        }
        self.observe(&path, &site);
        let alias_proven = self.bundler && found.via_paths && !found.directory_package;
        // A bundler resolves `.` and `..` like `./index`; Node does not prove them.
        let proven_relative = relative || (self.bundler && source.relative());
        if !type_only
            && !alias_proven
            && (!proven_relative || found.directory_package || common_lookup)
        {
            runtime = None;
            let reason = if common_lookup {
                format!("CommonJS runtime target is not proven: {specifier}")
            } else if found.directory_package && proven_relative {
                format!("Local directory runtime metadata is not proven: {specifier}")
            } else {
                format!("Local alias runtime conditions are not proven: {specifier}")
            };
            self.gap(&reason, None, module, GapKind::Resolution);
        }
        let file = match (&runtime, type_only) {
            (Some(runtime), false) => runtime.clone(),
            _ => path,
        };
        let import_id = r.import_id();
        match module_identity(self.namespace, &file) {
            Ok(target_module) => Target::Local {
                import_id,
                module: ModuleName::new(target_module),
                file,
                runtime_file: runtime,
                declaration_file: declaration,
            },
            Err(_) => {
                let reason = format!("Source path has no module identity: {file}");
                self.unresolved(r, &reason)
            }
        }
    }
}
