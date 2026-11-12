// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The record of one import: its id, subjects, data and evidence (`collect._import_record`). The
//! target comes from `import_target.rs`; the loop over the references is in `imports.rs`.

use archkeel_facts::data::ImportData;
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{package_of, stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{ImportFact, Record};

use super::import_target::Ref;
use super::Collection;
use crate::manifest::Lookup;
use crate::references::{Form, Reference};
use crate::source_input::{classify_specifier, ModuleFormat};

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
    /// Record one import.
    pub(super) fn import(
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
        let class = classify_specifier(specifier);
        let at = Ref {
            rel,
            module,
            reference,
            specifier,
            class,
            identity: &identity,
            evidence,
        };
        let target = self.target(&at, format);
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
        let site = crate::source::FileSite {
            rel: rel.to_owned(),
            line: reference.span.line,
            column: reference.span.column,
        };
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
}
