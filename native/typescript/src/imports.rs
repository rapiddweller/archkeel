// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One import record for each reference, with its target (`collect._references` and below).
//!
//! A reference that cannot be proven is an UNKNOWN gap, never a PASS: a computed specifier, a
//! setting that is not observed, a target that no rule covers.

use archkeel_facts::data::ImportData;
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{module_identity, package_of, stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{ImportFact, Record};

use super::{Collection, GapKind};
use crate::installed::installed;
use crate::kept::Kept;
use crate::kept_script::ScriptFile;
use crate::manifest::Lookup;
use crate::options::ModuleKind;
use crate::parse::{parse_for, Parsed};
use crate::plant;
use crate::references::{Form, Reference};
use crate::resolve::Found;
use crate::source_input::{
    classify_asset, classify_file, classify_specifier, ModuleFormat, SourceKind, SpecifierKind,
};
use archkeel_snapshot::paths::{dirname, join, within};

// The reserved identity of an asset edge; a colon cannot occur in an npm package name.
const BUNDLER_ASSET: &str = "bundler:asset";

/// Where an import was written: its evidence id and its module.
type Site = (String, String);

/// The import fact of the form of a reference.
pub(crate) fn fact(form: Form, data: ImportData) -> ImportFact {
    match form {
        Form::Import => ImportFact::Import(data),
        Form::Reexport => ImportFact::Reexport(data),
        Form::ImportEquals => ImportFact::ImportEquals(data),
        Form::DynamicImport => ImportFact::DynamicImport(data),
        Form::ImportType => ImportFact::ImportType(data),
        Form::Require => ImportFact::Require(data),
    }
}

impl Collection<'_> {
    /// `collect._selected`: a source file in scope that is not installed and not a test source.
    fn selected(&mut self, rel: &str) -> bool {
        !installed(&mut self.snapshot, rel)
            && self.roots.iter().any(|root| within(root, rel))
            && !self.excluded_test(rel)
    }

    /// Parse a file, report what it cannot prove, and record each of its references.
    pub(super) fn references(&mut self, rel: &str, module: &str, file_evidence: &str, text: &str) {
        let aliased = self.resolver.options.aliased();
        let mut parsed = parse_for(&mut self.parsers, rel, text.as_bytes(), aliased);
        if let Some(line) = parsed.first_error {
            let reason = format!("Syntax error in {rel}: unparseable construct at line {line}");
            self.gap(&reason, Some(file_evidence), module, GapKind::Collection);
        }
        for concern in &parsed.concerns {
            let evidence = self.cite(rel, &concern.span);
            self.gap(
                &concern.reason,
                Some(&evidence),
                module,
                GapKind::Collection,
            );
        }
        let format = self.resolver.format_of(&mut self.snapshot, rel);
        let explicit = self.resolver.options.module;
        // `collect._global_dependency_scope`: a file that is neither a declaration nor CommonJS.
        let suffix = classify_file(rel);
        let global_scope = suffix.is_some_and(|suffix| {
            suffix.source_kind() != Some(SourceKind::Declaration)
                && suffix.format_hint() != Some(ModuleFormat::Cjs)
        }) && matches!(format, Lookup::Missing | Lookup::Hit(ModuleFormat::Esm));
        let format_known = !matches!(format, Lookup::Missing);
        let script = ScriptFile::take(&mut parsed, format_known, global_scope);
        self.script_file_effects(rel, module, &script);
        let kept = Kept::from_parsed(module, &mut parsed, text, script);
        self.order.push(rel.to_owned());
        self.kept.insert(rel.to_owned(), kept);
        let cjs = classify_file(rel).and_then(|suffix| suffix.format_hint())
            == Some(ModuleFormat::Cjs)
            || explicit == Some(ModuleKind::CommonJs)
            || (format == Lookup::Hit(ModuleFormat::Cjs)
                && matches!(explicit, Some(ModuleKind::NodeNext | ModuleKind::Node16)));
        let mut handled = 0usize;
        for (index, reference) in parsed.references.iter().enumerate() {
            if plant::skip(rel, index) {
                continue;
            }
            let evidence = self.cite(rel, &reference.span);
            if reference.form == Form::Require && (!cjs || parsed.shadows_require) {
                let reason = "Unproven or shadowed require call";
                self.gap(reason, Some(&evidence), module, GapKind::Resolution);
            } else if reference.specifier.is_none() {
                let reason = format!("Computed {} cannot be resolved", reference.form.as_str());
                self.gap(&reason, Some(&evidence), module, GapKind::Resolution);
            } else {
                self.import(rel, module, reference, &evidence, &format);
            }
            handled += 1;
        }
        self.check_extracted(&parsed, handled, (rel, module, file_evidence));
    }

    /// The invariant of the extraction: each import-bearing node of the tree has a record or a gap.
    /// A node in a repaired part of the file has the gap of the syntax error. Any other node that
    /// has neither is a gap of its own, so a node that the extraction lost can never read as a
    /// complete scan.
    fn check_extracted(&mut self, parsed: &Parsed, handled: usize, file: (&str, &str, &str)) {
        let (rel, module, evidence) = file;
        let lost = parsed.places.saturating_sub(handled);
        if lost > 0 && parsed.first_error.is_none() {
            let reason = format!(
                "unextracted: {lost} import-bearing node(s) of {rel} have no record and no gap"
            );
            self.gap(&reason, Some(evidence), module, GapKind::Collection);
        }
    }

    /// Record one import.
    fn import(
        &mut self,
        rel: &str,
        module: &str,
        reference: &Reference,
        evidence: &str,
        format: &Lookup<ModuleFormat>,
    ) {
        let specifier = reference.specifier.as_deref().unwrap_or("");
        let form = reference.form.as_str();
        let line = reference.span.line;
        let parts = [
            Part::Text(module),
            Part::Number(line),
            Part::Number(reference.span.column),
            Part::Text(form),
        ];
        let identity = stable_id("IMP", &parts);
        let target = self.target(rel, module, reference, &identity, format);
        let (target_module, target_package) = match &target {
            Target::Local { module, .. } => {
                let module = module.as_str();
                (module.to_owned(), package_of(module).to_owned())
            }
            Target::Builtin { name, .. } => (name.clone(), name.clone()),
            Target::External { package, .. } => {
                (package.as_str().to_owned(), package.as_str().to_owned())
            }
            Target::Unresolved { specifier, .. } => (specifier.clone(), specifier.clone()),
        };
        let mut subjects: Vec<String> = [module, &target_module]
            .into_iter()
            .filter(|subject| !subject.is_empty())
            .map(str::to_owned)
            .collect();
        subjects.sort();
        let data = ImportData {
            source_module: ModuleName::new(module),
            source_package: PackageName::new(package_of(module)),
            target_module: ModuleName::new(target_module),
            target_package: PackageName::new(target_package),
            symbol: None,
            binding: None,
            symbols_known: false,
            specifier: Some(specifier.to_owned()),
            type_only: Some(reference.type_only),
            relative_level: 0,
            under_type_checking: reference.type_only,
            reexport: reference.form == Form::Reexport,
            module_level_import: reference.module_level,
            ..ImportData::statement()
        };
        let site = (rel.to_owned(), reference.span.line, reference.span.column);
        self.sites.insert(identity.clone(), site);
        self.targets.push(target);
        self.imports.push(Record {
            id: FactId::new(identity),
            evidence_class: EvidenceClass::Fact,
            area: Area::Source,
            title: format!("{module} imports {specifier}"),
            subjects,
            evidence_ids: vec![EvidenceId::new(evidence)],
            fact_ids: Vec::new(),
            data: fact(reference.form, data),
        });
    }

    fn unresolved(
        &mut self,
        module: &str,
        identity: &str,
        specifier: &str,
        reason: &str,
    ) -> Target {
        self.gap(reason, None, module, GapKind::Resolution);
        Target::Unresolved {
            import_id: FactId::new(identity),
            specifier: specifier.to_owned(),
            reason: reason.to_owned(),
        }
    }

    fn target(
        &mut self,
        rel: &str,
        module: &str,
        reference: &Reference,
        identity: &str,
        format: &Lookup<ModuleFormat>,
    ) -> Target {
        let specifier = reference.specifier.as_deref().unwrap_or("");
        let source = classify_specifier(specifier);
        let import_id = FactId::new(identity);
        if !reference.type_only && source.kind == SpecifierKind::Node && source.builtin() {
            return Target::Builtin {
                import_id,
                name: specifier.to_owned(),
            };
        }
        if reference.mode_override {
            let reason = format!("Resolution mode override is not observed: {specifier}");
            return self.unresolved(module, identity, specifier, &reason);
        }
        if let Some(blocked) = self.resolver.blocked.clone() {
            return self.unresolved(module, identity, specifier, &blocked.reason);
        }
        let known = !matches!(format, Lookup::Missing);
        let mode = match format {
            Lookup::Unknown(unknown) => {
                return self.unresolved(module, identity, specifier, &unknown.reason);
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
        let found = self
            .resolver
            .resolve(&mut self.snapshot, specifier, rel, mode, prefer_builtin);
        match found {
            Lookup::Unknown(unknown) => {
                if self.bundler && unknown.package_internal && source.npm_package() {
                    // The bundler picks the file inside the package; the package is the dependency.
                    return Target::External {
                        import_id,
                        package: PackageName::new(source.package),
                    };
                }
                self.unresolved(module, identity, specifier, &unknown.reason)
            }
            Lookup::Missing => {
                if source.builtin() {
                    return Target::Builtin {
                        import_id,
                        name: specifier.to_owned(),
                    };
                }
                if let Some(asset) = self
                    .bundler
                    .then(|| self.bundler_asset(rel, identity, specifier))
                    .flatten()
                {
                    return asset;
                }
                let reason = format!("Unresolved module: {specifier}");
                self.unresolved(module, identity, specifier, &reason)
            }
            Lookup::Hit(found) => self.local(rel, module, reference, identity, &found),
        }
    }

    /// An existing asset that a bundler loads itself; a missing one stays an unresolved module.
    fn bundler_asset(&mut self, rel: &str, identity: &str, specifier: &str) -> Option<Target> {
        let path = classify_asset(specifier)?;
        let source = classify_specifier(specifier);
        let import_id = FactId::new(identity);
        let asset = || Target::External {
            import_id: FactId::new(identity),
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
                package: PackageName::new(source.package),
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

    fn excluded_test_target(
        &mut self,
        module: &str,
        reference: &Reference,
        identity: &str,
        path: &str,
        site: &Site,
    ) -> Target {
        let specifier = reference.specifier.as_deref().unwrap_or("");
        if !self.observe(path, site) {
            let reason = format!("Excluded test source is unavailable: {path}");
            return self.unresolved(module, identity, specifier, &reason);
        }
        Target::Unresolved {
            import_id: FactId::new(identity),
            specifier: specifier.to_owned(),
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
    fn local(
        &mut self,
        rel: &str,
        module: &str,
        reference: &Reference,
        identity: &str,
        found: &Found,
    ) -> Target {
        let specifier = reference.specifier.as_deref().unwrap_or("");
        let source = classify_specifier(specifier);
        let path = found.path.clone();
        let suffix = classify_file(&path);
        let site: Site = (self.cite(rel, &reference.span), module.to_owned());
        if self.excluded_test(&path) && !installed(&mut self.snapshot, &path) {
            return self.excluded_test_target(module, reference, identity, &path, &site);
        }
        if !self.snapshot.readable(&path) {
            let reason = format!("Unavailable local target: {specifier}");
            return self.unresolved(module, identity, specifier, &reason);
        }
        let installed = path.split('/').any(|segment| segment == "node_modules");
        if installed || (!self.selected(&path) && found.external) {
            let reason = if source.kind == SpecifierKind::Imports {
                format!("External package alias identity is not observed: {specifier}")
            } else if source.relative() {
                format!("Unidentified external package: {specifier}")
            } else {
                let import_id = FactId::new(identity);
                return Target::External {
                    import_id,
                    package: PackageName::new(source.package),
                };
            };
            return self.unresolved(module, identity, specifier, &reason);
        }
        let in_source = suffix.is_some_and(|suffix| suffix.source_kind().is_some());
        if self.bundler && !(self.selected(&path) && in_source) {
            let import_id = FactId::new(identity);
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
                    package: PackageName::new(source.package),
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
        let import_id = FactId::new(identity);
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
                self.unresolved(module, identity, specifier, &reason)
            }
        }
    }
}
