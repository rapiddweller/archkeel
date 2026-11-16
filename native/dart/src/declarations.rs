// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Declaration assembly after preparation and parameter resolution (AD-392).

mod assembly;
mod members;
pub(crate) mod types;
pub(crate) mod work;

use crate::syntax::DefinitionKind as D;
use crate::syntax::{Definition, DefinitionKind};
use archkeel_facts::vocab::ExceptionName;
use assembly::identity;
pub(crate) use assembly::{Assembly, Output};
use std::collections::{BTreeMap, BTreeSet};
use types::{Category, Constructor, Data, Detail, File, Input, Kind};
use work::Stop;

/// A failure discards all partial records and indices. A caller cannot mistake a prefix for facts.
pub(crate) fn build(input: &Input) -> Output {
    let mut assembly = Assembly::default();
    if let Err(stop) = assembly
        .work
        .input(input)
        .and_then(|()| assembly.build_declaration_records(input))
    {
        let (_, gap) = crate::records::gap(
            ".",
            1,
            ExceptionName::UnsupportedDeclaration,
            stop.message(),
            None,
        );
        return Output {
            gaps: vec![gap],
            work: assembly.work.spent(),
            ..Output::default()
        };
    }
    let Assembly {
        mut output,
        evidence,
        gaps,
        ids,
        names,
        symbols,
        work,
    } = assembly;
    output.evidence = evidence.into_values().collect();
    output.gaps = gaps.into_values().collect();
    output.definition_ids = ids.into_iter().collect();
    output.definition_names = names.into_iter().collect();
    output.symbol_by_name = symbols.into_iter().collect();
    output.work = work.spent();
    output
}

impl Assembly {
    pub(crate) fn build_declaration_records(&mut self, input: &Input) -> Result<(), Stop> {
        let mut files: Vec<_> = input.files.iter().collect();
        for file in &files {
            self.work.charge(1)?;
            self.work.text(&file.rel)?;
        }
        files.sort_by(|a, b| a.rel.cmp(&b.rel));
        let mut previous = None;
        for file in files {
            self.work.charge(1)?;
            if previous == Some(&file.rel) {
                return Err(Stop::Input);
            }
            previous = Some(&file.rel);
            self.file(file)?;
        }
        Ok(())
    }

    fn file(&mut self, file: &File) -> Result<(), Stop> {
        let mut constructors = BTreeMap::new();
        for resolution in &file.constructors {
            self.work.charge(1)?;
            if constructors.insert(resolution.start, resolution).is_some() {
                return Err(Stop::Input);
            }
        }
        let expected = self.constructor_starts(file)?;
        self.work
            .charge(expected.len().saturating_add(constructors.len()))?;
        if !expected.iter().copied().eq(constructors.keys().copied()) {
            return Err(Stop::Input);
        }
        for definition in &file.syntax.definitions {
            self.work.charge(1)?;
            self.definition(file, definition, &constructors)?;
        }
        Ok(())
    }

    fn constructor_starts(&self, file: &File) -> Result<BTreeSet<usize>, Stop> {
        let mut starts = BTreeSet::new();
        for definition in &file.syntax.definitions {
            self.work.charge(1)?;
            if definition.span.start_byte > definition.span.end_byte
                || definition.span.end_byte > file.source_len
            {
                return Err(Stop::Input);
            }
            match definition.kind {
                D::Class | D::Interface | D::Mixin | D::Enum => {}
                D::Extension
                | D::ExtensionType
                | D::Typedef
                | D::Function
                | D::Getter
                | D::Setter
                | D::Variable => continue,
            }
            for member in &definition.members {
                self.constructor_start(member, &mut starts)?;
            }
        }
        Ok(starts)
    }

    fn constructor_start(
        &self,
        member: &crate::syntax::Member,
        starts: &mut BTreeSet<usize>,
    ) -> Result<(), Stop> {
        self.work.charge(1)?;
        if member.kind == crate::syntax::MemberKind::Constructor
            && !starts.insert(member.span.start_byte)
        {
            return Err(Stop::Input);
        }
        Ok(())
    }

    fn definition(
        &mut self,
        file: &File,
        definition: &Definition,
        resolutions: &BTreeMap<usize, &Constructor>,
    ) -> Result<(), Stop> {
        self.work.copies(definition)?;
        let qualified = format!("{}.{}", file.module, definition.name);
        self.work.text(&qualified)?;
        let (kind, category) = match definition.kind {
            D::Class | D::Interface | D::Mixin | D::Enum => (Kind::Class, Category::Class),
            D::Function | D::Getter | D::Setter => (Kind::Function, Category::Function),
            D::Typedef => (Kind::Alias, Category::TypeAlias),
            D::Variable => (Kind::Attribute, Category::Attribute),
            D::Extension | D::ExtensionType => {
                self.unsupported(file, definition, &qualified)?;
                return Ok(());
            }
        };
        let identity_kind = if definition.kind == D::Variable {
            "variable"
        } else {
            kind.as_ref()
        };
        let identity = identity(&file.rel, &definition.span, &qualified, identity_kind);
        self.index(file, &definition.span, &identity, None);
        let mut data = self.meta(
            file,
            &definition.name,
            &qualified,
            None,
            category,
            definition.visibility,
        )?;
        data.modifiers = Some(definition.modifiers.clone());
        let mut published = qualified.clone();
        let mut published_kind = kind;
        match definition.kind {
            D::Class | D::Interface | D::Mixin | D::Enum => {
                data.detail = self.class(file, definition, &qualified, &identity, resolutions)?;
            }
            D::Function | D::Getter | D::Setter => {
                published = self.top_callable(definition, &mut data)?;
            }
            D::Typedef => {
                data.detail = Detail::Value {
                    annotation: definition.alias.clone(),
                    constant: None,
                }
            }
            D::Variable => {
                published_kind = if definition.constant {
                    Kind::Constant
                } else {
                    Kind::Attribute
                };
                data.symbol_category = if definition.constant {
                    Category::Constant
                } else {
                    Category::Attribute
                };
                data.detail = Detail::Value {
                    annotation: definition.return_type.clone(),
                    constant: if definition.constant {
                        definition.literal.clone()
                    } else {
                        None
                    },
                };
            }
            D::Extension | D::ExtensionType => return Err(Stop::Input),
        }
        self.publish(
            file,
            &definition.span,
            identity.clone(),
            published_kind,
            data,
        );
        self.names.insert(
            (file.rel.clone(), definition.span.start_byte),
            published.clone(),
        );
        if matches!(definition.kind, D::Function | D::Getter | D::Setter) {
            let end = self.scope_end(file, definition)?;
            self.output.scope_candidates.push((
                file.rel.clone(),
                definition.name.clone(),
                published,
                identity,
                definition.span.clone(),
                definition.span.start_byte,
                end,
            ));
        }
        Ok(())
    }

    fn unsupported(
        &mut self,
        file: &File,
        definition: &Definition,
        qualified: &str,
    ) -> Result<(), Stop> {
        self.work.text(file.first_line.as_deref().unwrap_or(""))?;
        let word = if definition.kind == DefinitionKind::Extension {
            "extension"
        } else {
            "extension_type"
        };
        let message = format!("declaration kind '{word}' is not represented");
        let id = identity(&file.rel, &definition.span, qualified, word);
        self.index(file, &definition.span, &id, None);
        self.gap(
            file,
            &definition.span,
            ExceptionName::UnsupportedDeclaration,
            &message,
        );
        Ok(())
    }

    fn scope_end(&self, file: &File, definition: &Definition) -> Result<usize, Stop> {
        let mut end = file.source_len;
        for candidate in &file.syntax.definitions {
            self.work.charge(1)?;
            if candidate.span.start_byte > definition.span.start_byte {
                end = end.min(candidate.span.start_byte);
            }
        }
        Ok(end)
    }

    fn top_callable(&mut self, definition: &Definition, data: &mut Data) -> Result<String, Stop> {
        let parameters = self.parameters(&definition.parameters)?;
        let accessor = match definition.kind {
            D::Getter => Some("getter"),
            D::Setter => Some("setter"),
            D::Function => None,
            D::Class
            | D::Interface
            | D::Mixin
            | D::Enum
            | D::Extension
            | D::ExtensionType
            | D::Typedef
            | D::Variable => return Err(Stop::Input),
        };
        if let Some(accessor) = accessor {
            data.qualified_name = format!("{}::{accessor}", data.qualified_name);
        }
        let returns = if definition.kind == D::Setter && definition.return_type.is_none() {
            Some("void".to_owned())
        } else {
            definition.return_type.clone()
        };
        self.work.charge(parameters.len())?;
        data.signature_complete = parameters.iter().all(|p| p.default_known);
        data.detail = Detail::Callable {
            annotation: None,
            returns,
            parameters,
            method_kind: archkeel_facts::vocab::MethodKind::Static,
            signature_decorators_proven: true,
            accessor_kind: accessor.map(|_| definition.kind),
        };
        Ok(data.qualified_name.clone())
    }
}
