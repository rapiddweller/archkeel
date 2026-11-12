// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Import records and base declarations from closed, typed resolver answers.

use super::types::{DirectiveTarget, ImportData, RecordKind};
use super::{decl, fact, id, package, Builder, Stop};
use crate::syntax::{Combinator, DefinitionKind, Directive, DirectiveKind, Visibility};
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::Part;
use archkeel_facts::ids::{EvidenceId, FactId, ModuleName, PackageName};
use archkeel_facts::vocab::Status;
use std::collections::BTreeSet;

impl Builder<'_> {
    pub(super) fn imports(&mut self) -> Result<(), Stop> {
        for source in &self.input.files {
            let rel = &source.file.rel;
            self.decl.work.charge(1)?;
            if !self.parsed.contains(rel) {
                continue;
            }
            let module = self.file(rel)?.module.clone();
            for directive in &source.file.syntax.directives {
                self.decl.work.copies(directive)?;
                match directive.kind {
                    DirectiveKind::Import | DirectiveKind::Export => {}
                    DirectiveKind::Part | DirectiveKind::PartOf | DirectiveKind::Library => {
                        continue
                    }
                }
                let key = (rel.clone(), directive.span.start_byte);
                let answer = self
                    .directive_indices
                    .get(&key)
                    .and_then(|index| self.input.resolver.directives.get(*index))
                    .ok_or(Stop::Input)?;
                let selected = self.selected(directive)?;
                for target in &answer.targets {
                    self.decl.work.copies(target)?;
                    for symbol in &selected {
                        self.decl.work.charge(1)?;
                        self.import(
                            rel,
                            &module,
                            directive,
                            target,
                            symbol.as_deref(),
                            selected != [None],
                        )?;
                    }
                }
            }
        }
        Ok(())
    }

    fn selected(&self, directive: &Directive) -> Result<Vec<Option<String>>, Stop> {
        let mut selected: Option<BTreeSet<String>> = None;
        for (mode, values) in &directive.combinators {
            self.decl.work.copies(values)?;
            let names: BTreeSet<_> = values.iter().cloned().collect();
            selected = match (mode, selected) {
                (Combinator::Show, None) => Some(names),
                (Combinator::Show, Some(old)) => Some(old.intersection(&names).cloned().collect()),
                (Combinator::Hide, Some(old)) => Some(old.difference(&names).cloned().collect()),
                (Combinator::Hide, None) => None,
            };
        }
        match selected {
            Some(values) if !values.is_empty() => Ok(values.into_iter().map(Some).collect()),
            Some(_) | None => Ok(vec![None]),
        }
    }

    fn import(
        &mut self,
        rel: &str,
        module: &str,
        directive: &Directive,
        target: &DirectiveTarget,
        symbol: Option<&str>,
        known: bool,
    ) -> Result<(), Stop> {
        self.decl.work.text(module)?;
        self.decl.work.text(&target.module)?;
        let symbol_part = symbol.map_or(Part::Nothing, Part::Text);
        let identity = id(
            "DARTIMP",
            rel,
            directive.span.start_byte,
            &[Part::Text(&target.uri), symbol_part],
        );
        let cited = self.cite(rel, &directive.span)?;
        let target_module = &target.module;
        let qualified = symbol.map(|name| format!("{target_module}.{name}"));
        let data = ImportData {
            source_module: module.to_owned(),
            source_package: package(module),
            target_module: target_module.clone(),
            target_package: if target.rel_path.is_some() {
                package(target_module)
            } else {
                target.package.clone()
            },
            symbol: symbol.map(str::to_owned),
            binding: symbol.map(str::to_owned).or_else(|| {
                if directive.kind == DirectiveKind::Import {
                    directive.prefix.clone()
                } else {
                    None
                }
            }),
            symbols_known: known,
            relative_level: 0,
            under_type_checking: false,
            ordinary_module: true,
            module_level_import: true,
            reexport: directive.kind == DirectiveKind::Export,
            reexport_chain: qualified.iter().cloned().collect(),
            origin_definition: qualified,
            symbol_visibility: symbol.map(|name| match Visibility::of(name) {
                Visibility::Private => archkeel_facts::vocab::Visibility::Private,
                Visibility::Public => archkeel_facts::vocab::Visibility::PublicName,
            }),
        };
        self.output.imports.push(fact(
            identity.clone(),
            RecordKind::Import,
            format!("{module} imports {}", target.uri),
            vec![module.to_owned(), target_module.clone()],
            cited,
            data,
        ));
        let import_id = FactId::new(identity);
        let resolved = match &target.rel_path {
            Some(path) => Target::Local {
                import_id,
                module: ModuleName::new(target_module),
                file: path.clone(),
                runtime_file: None,
                declaration_file: None,
            },
            None if target.builtin => Target::Builtin {
                import_id,
                name: target_module.clone(),
            },
            None if target.package != self.input.package_name => Target::External {
                import_id,
                package: PackageName::new(&target.package),
            },
            None => Target::Unresolved {
                import_id,
                specifier: target.uri.clone(),
                reason: "target is not selected".to_owned(),
            },
        };
        self.output.targets.push(resolved);
        Ok(())
    }

    pub(super) fn bases(&mut self) -> Result<(), Stop> {
        for source in &self.input.files {
            self.decl.work.charge(1)?;
            let rel = &source.file.rel;
            if !self.parsed.contains(rel) {
                continue;
            }
            let module = self.file(rel)?.module.clone();
            for definition in &source.file.syntax.definitions {
                self.decl.work.copies(definition)?;
                match definition.kind {
                    DefinitionKind::Class
                    | DefinitionKind::Interface
                    | DefinitionKind::Mixin
                    | DefinitionKind::Enum => {}
                    DefinitionKind::Extension
                    | DefinitionKind::ExtensionType
                    | DefinitionKind::Typedef
                    | DefinitionKind::Function
                    | DefinitionKind::Getter
                    | DefinitionKind::Setter
                    | DefinitionKind::Variable => continue,
                }
                let qualified = format!("{module}.{}", definition.name);
                let Some(index) = self.symbol_index(&qualified) else {
                    continue;
                };
                let mut bases = Vec::new();
                for (kind, names) in [
                    (decl::BaseKind::Inherits, &definition.extends),
                    (decl::BaseKind::MixesIn, &definition.with_types),
                    (decl::BaseKind::Realizes, &definition.implements),
                ] {
                    self.decl.work.charge(1)?;
                    for name in names {
                        self.decl.work.text(name)?;
                        let targets = self.names(rel, name)?;
                        let target = match targets.as_slice() {
                            [one] => self.canonical_target(one)?,
                            _ => String::new(),
                        };
                        let target_record = self
                            .symbol_index(&target)
                            .and_then(|index| self.decl.output.symbols.get(index));
                        let is_class =
                            target_record.is_some_and(|record| record.kind == decl::Kind::Class);
                        let mixin = target_record.is_some_and(|record| match &record.data.detail {
                            decl::Detail::Class {
                                class_kind,
                                mixin_capable,
                                ..
                            } => {
                                *class_kind == decl::ClassKind::Mixin
                                    || *mixin_capable == Some(true)
                            }
                            decl::Detail::Callable { .. }
                            | decl::Detail::Value { .. }
                            | decl::Detail::Binding { .. } => false,
                        });
                        let resolved = is_class && (kind != decl::BaseKind::MixesIn || mixin);
                        bases.push(decl::Base {
                            id: FactId::new(id(
                                "DARTBASE",
                                rel,
                                definition.span.start_byte,
                                &[Part::Text(kind.as_str()), Part::Text(name)],
                            )),
                            relationship_kind: kind,
                            status: if resolved {
                                Status::Resolved
                            } else {
                                Status::Unresolved
                            },
                            targets: if resolved { vec![target] } else { Vec::new() },
                            candidate_count: if resolved { 1 } else { targets.len() },
                            candidates_truncated: false,
                            expression: name.clone(),
                            reason: if resolved {
                                "Analyzer resolved local declared type"
                            } else if kind == decl::BaseKind::MixesIn {
                                "with target is not proven to be a local mixin-capable declaration"
                            } else {
                                "base type is external or unresolved"
                            },
                            evidence_ids: vec![EvidenceId::new(self.cite(rel, &definition.span)?)],
                        });
                    }
                }
                self.decl
                    .output
                    .symbols
                    .get_mut(index)
                    .ok_or(Stop::Input)?
                    .data
                    .base_declarations = Some(bases);
            }
        }
        Ok(())
    }

    fn canonical_target(&self, qualified: &str) -> Result<String, Stop> {
        let record = self
            .symbol_index(qualified)
            .and_then(|index| self.decl.output.symbols.get(index));
        let Some(record) = record.filter(|record| record.kind == decl::Kind::Alias) else {
            return Ok(qualified.to_owned());
        };
        let annotation = match &record.data.detail {
            decl::Detail::Value { annotation, .. } => annotation,
            decl::Detail::Class { .. }
            | decl::Detail::Callable { .. }
            | decl::Detail::Binding { .. } => return Err(Stop::Input),
        };
        let Some(annotation) = annotation else {
            return Ok(qualified.to_owned());
        };
        let targets = self.names(&record.data.location.source_file, annotation)?;
        Ok(match targets.as_slice() {
            [one] => one.clone(),
            _ => qualified.to_owned(),
        })
    }
}
