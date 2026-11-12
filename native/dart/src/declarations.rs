// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Declaration assembly after preparation and parameter resolution (AD-390).

mod members;
pub(crate) mod types;
mod work;

use crate::syntax::DefinitionKind as D;
use crate::syntax::{Definition, DefinitionKind, ParameterKind as SyntaxParameterKind, Span};
use archkeel_facts::envelope::Evidence;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::sections::GapFact;
use archkeel_facts::vocab::ExceptionName;
use archkeel_facts::Record;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use types::*;
use work::{Stop, Work};

#[derive(Default, Serialize)]
pub(crate) struct Output {
    symbols: Vec<Symbol>,
    evidence: Vec<Evidence>,
    gaps: Vec<Record<GapFact>>,
    definition_ids: Vec<((String, usize, usize), String)>,
    definition_names: Vec<((String, usize), String)>,
    scope_candidates: Vec<Scope>,
    symbol_by_name: Vec<(String, String)>,
    incomplete_inventory_ids: Vec<String>,
    work: usize,
}

#[derive(Default)]
struct Assembly {
    output: Output,
    evidence: BTreeMap<String, Evidence>,
    gaps: BTreeMap<String, Record<GapFact>>,
    ids: BTreeMap<(String, usize, usize), String>,
    names: BTreeMap<(String, usize), String>,
    symbols: BTreeMap<String, String>,
    work: Work,
}

/// A failure discards all partial records and indices. A caller cannot mistake a prefix for facts.
pub(crate) fn build(input: &Input) -> Output {
    let mut assembly = Assembly::default();
    if let Err(stop) = assembly.run(input) {
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
    fn run(&mut self, input: &Input) -> Result<(), Stop> {
        self.work.value(input)?;
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
        let kind = match definition.kind {
            D::Class | D::Interface | D::Mixin | D::Enum => Kind::Class,
            D::Function | D::Getter | D::Setter => Kind::Function,
            D::Typedef => Kind::Alias,
            D::Variable => Kind::Attribute,
            D::Extension | D::ExtensionType => {
                self.unsupported(file, definition, &qualified)?;
                return Ok(());
            }
        };
        let identity_kind = if definition.kind == D::Variable {
            "variable"
        } else {
            kind.as_str()
        };
        let identity = identity(&file.rel, &definition.span, &qualified, identity_kind);
        self.index(file, &definition.span, &identity, None);
        let category = match kind {
            Kind::Class => Category::Class,
            Kind::Function => Category::Function,
            Kind::Alias => Category::TypeAlias,
            Kind::Attribute => Category::Attribute,
            Kind::Method => Category::Method,
            Kind::Constant => Category::Constant,
        };
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

    fn meta(
        &mut self,
        file: &File,
        name: &str,
        qualified: &str,
        parent: Option<(&str, &str)>,
        category: Category,
        visibility: crate::syntax::Visibility,
    ) -> Result<Data, Stop> {
        self.work.text(&file.rel)?;
        self.work.text(&file.module)?;
        self.work.text(name)?;
        self.work.text(qualified)?;
        if let Some((name, id)) = parent {
            self.work.text(name)?;
            self.work.text(id)?;
        }
        Ok(Data {
            qualified_name: qualified.to_owned(),
            location: Location {
                module: archkeel_facts::ids::ModuleName::new(&file.module),
                source_file: file.rel.clone(),
                package: archkeel_facts::ids::PackageName::new(
                    file.module
                        .rsplit_once('.')
                        .map_or("", |(package, _)| package),
                ),
            },
            name: name.to_owned(),
            parent: parent.map(|(name, _)| name.to_owned()),
            lexical_parent_id: parent.map(|(_, id)| archkeel_facts::ids::FactId::new(id)),
            visibility_detail: VisibilityDetail {
                kind: visibility,
                basis: "language",
                spelling: name.rsplit('.').next().unwrap_or(name).to_owned(),
            },
            symbol_category: category,
            source_binding_unique: true,
            source_member_binding_static: true,
            class_header_static: true,
            decorators: Vec::new(),
            signature_complete: true,
            overload_signature: false,
            modifiers: None,
            detail: Detail::Value {
                annotation: None,
                constant: None,
            },
        })
    }

    fn parameters(
        &mut self,
        parameters: &[crate::syntax::Parameter],
    ) -> Result<Vec<Parameter>, Stop> {
        let mut result = Vec::new();
        for parameter in parameters {
            self.work.copies(parameter)?;
            result.push(Parameter {
                name: parameter.name.clone(),
                annotation: parameter.annotation.clone(),
                kind: parameter_kind(parameter.kind),
                default: parameter
                    .default
                    .clone()
                    .or_else(|| parameter.optional.then(|| "null".to_owned())),
                default_known: parameter.default_known,
                super_formal: None,
                evidence_ids: None,
            });
        }
        Ok(result)
    }

    fn index(&mut self, file: &File, span: &Span, id: &str, qualified: Option<&str>) {
        self.ids
            .insert((file.rel.clone(), span.line, span.column), id.to_owned());
        if let Some(qualified) = qualified {
            self.names
                .insert((file.rel.clone(), span.start_byte), qualified.to_owned());
        }
    }

    fn cite(&mut self, file: &File, span: &Span) -> String {
        let evidence = Evidence::at(
            &file.rel,
            number(span.line),
            number(span.end_line),
            number(span.column),
            &span.excerpt,
        );
        let id = evidence.id.as_str().to_owned();
        self.evidence.insert(id.clone(), evidence);
        id
    }

    fn gap(&mut self, file: &File, span: &Span, kind: ExceptionName, message: &str) {
        let (id, _) = crate::records::gap(&file.rel, span.line, kind, message, None);
        if self.gaps.contains_key(&id) {
            return;
        }
        let cited = self.gap_cite(file, span);
        let (id, gap) = crate::records::gap(&file.rel, span.line, kind, message, Some(cited));
        self.gaps.entry(id).or_insert(gap);
    }

    fn gap_cite(&mut self, file: &File, span: &Span) -> String {
        if !span.excerpt.is_empty() {
            return self.cite(file, span);
        }
        let first = file.first_line.as_deref().map_or("", crate::pytext::rstrip);
        let line = if first.is_empty() { 0 } else { 1 };
        let evidence = Evidence::at(&file.rel, line, line, 0, first);
        let id = evidence.id.as_str().to_owned();
        self.evidence.insert(id.clone(), evidence);
        id
    }

    fn publish(&mut self, file: &File, span: &Span, id: String, kind: Kind, data: Data) {
        let qualified = data.qualified_name.clone();
        let cited = self.cite(file, span);
        self.symbols.insert(qualified.clone(), id.clone());
        self.output.symbols.push(Symbol {
            id: archkeel_facts::ids::FactId::new(id),
            evidence_class: archkeel_facts::vocab::EvidenceClass::Fact,
            area: archkeel_facts::vocab::Area::Source,
            kind,
            title: format!("{qualified} declaration"),
            subjects: vec![qualified],
            evidence_ids: vec![archkeel_facts::ids::EvidenceId::new(cited)],
            fact_ids: [],
            rule_ids: [],
            provenance: [],
            data,
        });
    }
}

fn parameter_kind(kind: SyntaxParameterKind) -> ParameterKind {
    match kind {
        SyntaxParameterKind::Named => ParameterKind::KeywordOnly,
        SyntaxParameterKind::Positional => ParameterKind::Positional,
    }
}

fn number(value: usize) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}

fn identity(rel: &str, span: &Span, qualified: &str, kind: &str) -> String {
    stable_id(
        "DARTDEF",
        &[
            Part::Text(rel),
            Part::Number(number(span.start_byte)),
            Part::Text(qualified),
            Part::Text(kind),
        ],
    )
}
