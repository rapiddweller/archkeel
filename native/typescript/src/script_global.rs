// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A global that the platform, a `declare`, a vendored library or a namespace publishes
//! (`collect._script_external_dependency`, `_script_standard_global`, `_script_declared_global`,
//! `_script_vendor_package`, `_script_namespace_dependency`, `_script_global_stable`).

use archkeel_facts::data::BindingData;
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{FactId, ModuleName, PackageName};

use crate::script_deps::{Probe, Run};
use crate::script_project::{Publisher, HOST_NAMES};
use crate::script_records::{binding, global_id, import_record, Use};
use crate::script_types::ScriptAlias;
use crate::source::Span;

impl<'a, 'p> Run<'a, 'p> {
    /// `_script_global_stable`: nothing in the project or in a vendor publishes or writes the name.
    fn global_stable(&self, name: &str, publishers: &[Publisher]) -> bool {
        let paths = &self.project.paths;
        publishers.is_empty()
            && self.vendors.complete
            && !self.vendors.unbounded
            && !self.vendors.writes.contains(name)
            && !self.vendors.packages.contains_key(name)
            && !self.partial
            && !self.project.any_error
            && !(paths.any_empty || paths.singles.contains_key(name))
    }

    /// `_script_standard_global`.
    fn standard_global(&self, name: &str, publishers: &[Publisher]) -> bool {
        self.standard.contains(name)
            && self.global_stable(name, publishers)
            && !self.project.bound_in_scripts.contains_key(name)
    }

    /// `_script_declared_global`: the first `declare` of the name in the project, when nothing else
    /// binds or writes it.
    fn declared_global(&self, name: &str, publishers: &[Publisher]) -> Option<(&'a str, &'a Span)> {
        let declared = self.project.declared.get(name)?;
        let (rel, _) = self.project.files.get(declared.file)?;
        let free = !declared.bound_elsewhere && self.global_stable(name, publishers);
        free.then_some((*rel, declared.span))
    }

    /// `_script_vendor_package`: the package of the one vendor that publishes the name.
    fn vendor_package(&self, name: &str, publishers: &[Publisher]) -> Option<String> {
        let packages = self
            .vendors
            .packages
            .get(name)
            .map_or(&[][..], Vec::as_slice);
        let host = || HOST_NAMES.iter().copied();
        let writes = &self.vendors.writes;
        let collides = writes.contains(name) || host().any(|n| writes.contains(n));
        let paths = &self.project.paths;
        let bound = self.project.bound_anywhere.contains_key(name)
            || host().any(|n| self.project.bound_anywhere.contains_key(n));
        let written = paths.any_empty
            || paths.singles.contains_key(name)
            || host().any(|n| paths.singles.contains_key(n))
            || paths.loader_first;
        let blocked = !publishers.is_empty()
            || packages.len() != 1
            || self.vendors.unbounded
            || collides
            || self.project.any_error
            || bound
            || written;
        if blocked {
            return None;
        }
        packages.first().cloned()
    }

    /// `_script_external_dependency`.
    pub fn external_dependency(
        &mut self,
        rel: &str,
        probe: &Probe,
        path: &[String],
        alias: Option<&ScriptAlias>,
        publishers: &[Publisher<'a>],
    ) -> bool {
        let module = self.module(rel);
        let identity = global_id(&module, probe.kind, &probe.span);
        let first = path.first().map_or("", String::as_str);
        let mut facts: Vec<String> = Vec::new();
        let package;
        if self.standard_global(first, publishers) {
            self.sink.targets.push(Target::Builtin {
                import_id: FactId::new(identity),
                name: first.to_owned(),
            });
            package = first.to_owned();
        } else if let Some((declared_rel, span)) = self.declared_global(first, publishers) {
            self.sink.targets.push(Target::Builtin {
                import_id: FactId::new(identity),
                name: first.to_owned(),
            });
            package = first.to_owned();
            // The declaration sits in another file, so it is a fact, not evidence of this record.
            facts.push(self.declaration_fact(declared_rel, span, first));
        } else if let Some(vendor) = self.vendor_package(first, publishers) {
            self.sink.targets.push(Target::External {
                import_id: FactId::new(identity),
                package: PackageName::new(vendor.clone()),
            });
            package = vendor;
        } else {
            return false;
        }
        let evidence = vec![self.sink.cite(rel, &probe.span)];
        let record = Use {
            module: &module,
            kind: probe.kind,
            span: &probe.span,
            path,
            target_module: &package,
            target_package: Some(&package),
            symbol: None,
            known: false,
            evidence,
            binding: alias.map(|alias| alias.name.as_str()),
            facts: self.fact_ids_with(&module, probe, facts),
        };
        self.sink.imports.push(import_record(&record));
        true
    }

    /// The facts that already prove a site, and `more`.
    fn fact_ids_with(&self, module: &str, probe: &Probe, more: Vec<String>) -> Vec<String> {
        let mut all = self.sink.facts.fact_ids(module, &probe.key());
        all.extend(more);
        all
    }

    /// `_script_declaration_fact`.
    fn declaration_fact(&mut self, rel: &str, span: &Span, name: &str) -> String {
        let module = self.module(rel);
        let parts = [
            Part::Text(&module),
            Part::Number(span.line),
            Part::Number(span.column),
            Part::Text(name),
        ];
        let identity = stable_id("SCRIPTDECLARATION", &parts);
        let evidence = vec![self.sink.cite(rel, span)];
        let data = BindingData {
            binding: Some(name.to_owned()),
            script_global: Some(name.to_owned()),
            ..BindingData::in_module(&module)
        };
        let title = format!("{module} declares script global {name}");
        self.sink
            .facts
            .publish(binding(identity.clone(), title, &module, evidence, data));
        identity
    }

    /// `_script_namespace_dependency`: a use of a namespace that one file declares.
    pub fn namespace_dependency(
        &mut self,
        rel: &str,
        probe: &Probe,
        path: &[String],
        alias: Option<&ScriptAlias>,
        publishers: &[Publisher<'a>],
    ) -> bool {
        let first = path.first().map_or("", String::as_str);
        let found = self
            .project
            .namespaces
            .get(first)
            .map_or(&[][..], Vec::as_slice);
        let [(source_at, namespace)] = found else {
            return false;
        };
        let paths = &self.project.paths;
        let blocked = self.project.any_error
            || paths.any_empty
            || self.project.bound_or_written_elsewhere(first, *source_at);
        if !publishers.is_empty() || blocked {
            return false;
        }
        let Some((source_rel, _)) = self.project.files.get(*source_at).copied() else {
            return false;
        };
        let module = self.module(rel);
        let target = self.module(source_rel);
        let identity = global_id(&module, probe.kind, &probe.span);
        let parts = [
            Part::Text(&target),
            Part::Text(&namespace.name),
            Part::Number(namespace.span.line),
        ];
        let proof = stable_id("SCRIPT_NAMESPACE_SOURCE", &parts);
        let evidence = vec![
            self.sink.cite(source_rel, &namespace.span),
            self.sink.cite(source_rel, &namespace.initialization),
        ];
        let data = BindingData {
            binding: Some(namespace.name.clone()),
            script_namespace: Some(namespace.name.clone()),
            ..BindingData::in_module(&target)
        };
        let record = binding(
            proof.clone(),
            "Script namespace source binding".to_owned(),
            &target,
            evidence,
            data,
        );
        self.sink.facts.publish(record);
        self.sink
            .facts
            .module(&module)
            .fact_ids
            .insert(probe.key(), vec![proof]);
        self.sink.targets.push(Target::Local {
            import_id: FactId::new(identity),
            module: ModuleName::new(target.clone()),
            file: source_rel.to_owned(),
            runtime_file: None,
            declaration_file: None,
        });
        if let Some(member) = path.get(1) {
            let reason =
                format!("Script namespace member {first}.{member} is not statically published");
            let cited = self.sink.cite(rel, &probe.span);
            self.sink.gap(&reason, &[cited], &module);
        }
        let evidence = vec![self.sink.cite(rel, &probe.span)];
        let single = path.len() == 1;
        let record = Use {
            module: &module,
            kind: probe.kind,
            span: &probe.span,
            path,
            target_module: &target,
            target_package: None,
            symbol: path.get(usize::from(!single)).map(String::as_str),
            known: single,
            evidence,
            binding: alias.map(|alias| alias.name.as_str()),
            facts: self.sink.facts.fact_ids(&module, &probe.key()),
        };
        self.sink.imports.push(import_record(&record));
        true
    }
}
