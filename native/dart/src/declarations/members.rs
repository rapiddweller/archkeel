// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Class members and resolved parameter records, without a second resolver.

use super::types::*;
use super::work::Stop;
use super::{identity, number, parameter_kind, Assembly};
use crate::syntax::{Definition, DefinitionKind, Member, MemberKind, Modifier, Span, Visibility};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::FactId;
use archkeel_facts::vocab::{ExceptionName, MethodKind};
use std::collections::BTreeMap;

impl Assembly {
    pub(super) fn class(
        &mut self,
        file: &File,
        definition: &Definition,
        qualified: &str,
        identity: &str,
        resolutions: &BTreeMap<usize, &Constructor>,
    ) -> Result<Detail, Stop> {
        use DefinitionKind as D;
        let class_kind = match definition.kind {
            D::Class => ClassKind::Class,
            D::Interface => ClassKind::Protocol,
            D::Mixin => ClassKind::Mixin,
            D::Enum => ClassKind::Enum,
            D::Extension
            | D::ExtensionType
            | D::Typedef
            | D::Function
            | D::Getter
            | D::Setter
            | D::Variable => return Err(Stop::Input),
        };
        let mut attributes = Vec::new();
        let mut methods = Vec::new();
        if definition.kind == D::Enum {
            if definition.enum_members.len() != definition.enum_member_spans.len() {
                return Err(Stop::Input);
            }
            for (literal, span) in definition
                .enum_members
                .iter()
                .zip(&definition.enum_member_spans)
            {
                self.work.charge(1)?;
                attributes.push(self.attribute(
                    file,
                    span,
                    qualified,
                    literal,
                    None,
                    true,
                    None,
                    Visibility::of(literal),
                )?);
            }
        }
        for member in &definition.members {
            self.work.copies(member)?;
            match member.kind {
                MemberKind::Field => attributes.push(self.attribute(
                    file,
                    &member.span,
                    qualified,
                    &member.name,
                    member.annotation.clone(),
                    member.r#static,
                    if member.constant {
                        member.initializer.clone()
                    } else {
                        None
                    },
                    member.visibility,
                )?),
                MemberKind::Method
                | MemberKind::Constructor
                | MemberKind::Getter
                | MemberKind::Setter
                | MemberKind::Operator => methods.push(self.member(
                    file,
                    definition,
                    qualified,
                    identity,
                    member,
                    resolutions,
                )?),
            }
        }
        self.work.charge(attributes.len())?;
        let fields = attributes
            .iter()
            .map(|attribute| attribute.definition_id.clone())
            .collect();
        self.work.charge(definition.modifiers.len())?;
        Ok(Detail::Class {
            class_kind,
            enum_members: definition.enum_members.clone(),
            attribute_declarations: attributes,
            member_inventories: vec![
                Inventory::new(InventoryKind::Attribute, fields),
                Inventory::new(
                    InventoryKind::Method,
                    methods.into_iter().map(FactId::new).collect(),
                ),
            ],
            mixin_capable: match definition.kind {
                D::Class | D::Mixin => Some(
                    definition.kind == D::Mixin || definition.modifiers.contains(&Modifier::Mixin),
                ),
                D::Interface | D::Enum => None,
                D::Extension
                | D::ExtensionType
                | D::Typedef
                | D::Function
                | D::Getter
                | D::Setter
                | D::Variable => return Err(Stop::Input),
            },
        })
    }

    fn member(
        &mut self,
        file: &File,
        definition: &Definition,
        parent: &str,
        parent_id: &str,
        member: &Member,
        resolutions: &BTreeMap<usize, &Constructor>,
    ) -> Result<String, Stop> {
        let constructor = member.kind == MemberKind::Constructor;
        let spelling = if constructor {
            member.name.rsplit('.').next().unwrap_or(&member.name)
        } else {
            &member.name
        };
        let (accessor, suffix) = match member.kind {
            MemberKind::Getter => (Some(DefinitionKind::Getter), "::getter"),
            MemberKind::Setter => (Some(DefinitionKind::Setter), "::setter"),
            MemberKind::Field
            | MemberKind::Method
            | MemberKind::Constructor
            | MemberKind::Operator => (None, ""),
        };
        self.work.text(parent)?;
        let qualified = format!("{parent}.{spelling}{suffix}");
        let id = identity(&file.rel, &member.span, &qualified, "method");
        let owner = self.owner(file, definition)?;
        let parameters = if constructor {
            self.resolved_parameters(
                file,
                member,
                &id,
                resolutions
                    .get(&member.span.start_byte)
                    .copied()
                    .ok_or(Stop::Input)?,
            )?
        } else {
            self.parameters(&member.parameters)?
        };
        let returns = if constructor {
            match owner {
                Some(owner) if !owner.type_parameters.is_empty() => {
                    self.work.copies(&owner.type_parameters)?;
                    Some(format!(
                        "{}<{}>",
                        definition.name,
                        owner.type_parameters.join(", ")
                    ))
                }
                Some(_) | None => Some(definition.name.clone()),
            }
        } else if member.kind == MemberKind::Setter && member.return_type.is_none() {
            Some("void".to_owned())
        } else {
            member.return_type.clone()
        };
        self.work.charge(parameters.len())?;
        let complete = parameters.iter().all(|parameter| parameter.default_known);
        let mut data = self.meta(
            file,
            &member.name,
            &qualified,
            Some((parent, parent_id)),
            Category::Method,
            member.visibility,
        )?;
        data.signature_complete = complete;
        data.detail = Detail::Callable {
            annotation: None,
            returns,
            parameters,
            method_kind: if member.factory {
                MethodKind::Factory
            } else if constructor {
                MethodKind::Constructor
            } else if member.r#static {
                MethodKind::Static
            } else {
                MethodKind::Instance
            },
            signature_decorators_proven: true,
            accessor_kind: accessor,
        };
        self.publish(file, &member.span, id.clone(), Kind::Method, data);
        self.index(file, &member.span, &id, Some(&qualified));
        let (start, end) = owner.map_or((member.span.start_byte, member.span.end_byte), |owner| {
            (owner.span.start_byte, owner.span.end_byte)
        });
        self.output.scope_candidates.push((
            file.rel.clone(),
            member.name.clone(),
            qualified,
            id.clone(),
            member.span.clone(),
            start,
            end,
        ));
        Ok(id)
    }

    fn resolved_parameters(
        &mut self,
        file: &File,
        member: &Member,
        identity: &str,
        resolution: &Constructor,
    ) -> Result<Vec<Parameter>, Stop> {
        if resolution.parameters.len() != member.parameters.len() {
            return Err(Stop::Input);
        }
        for problem in &resolution.problems {
            self.parameter_problem(file, member, identity, problem)?;
        }
        let mut formals = BTreeMap::new();
        for formal in &member.parameters {
            self.work.copies(formal)?;
            if formal.super_formal {
                formals.insert(&formal.name, &formal.span);
            }
        }
        let mut result = Vec::new();
        for (parameter, formal) in resolution.parameters.iter().zip(&member.parameters) {
            self.work.copies(parameter)?;
            if parameter.name != formal.name {
                return Err(Stop::Input);
            }
            let span = formals.get(&parameter.name);
            result.push(Parameter {
                name: parameter.name.clone(),
                annotation: parameter.annotation.clone(),
                kind: parameter_kind(parameter.kind),
                default: parameter.default.clone(),
                default_known: parameter.default_known,
                super_formal: span.map(|_| true),
                evidence_ids: span
                    .map(|span| vec![archkeel_facts::ids::EvidenceId::new(self.cite(file, span))]),
            });
        }
        Ok(result)
    }

    fn owner<'a>(
        &self,
        file: &'a File,
        definition: &Definition,
    ) -> Result<Option<&'a Definition>, Stop> {
        for candidate in &file.syntax.definitions {
            self.work.text(&candidate.name)?;
            if candidate.name == definition.name {
                return Ok(Some(candidate));
            }
        }
        Ok(None)
    }

    fn parameter_problem(
        &mut self,
        file: &File,
        member: &Member,
        identity: &str,
        problem: &Problem,
    ) -> Result<(), Stop> {
        self.work.copies(problem)?;
        if problem.path != file.rel {
            return Err(Stop::Input);
        }
        let span = problem.span.as_ref().unwrap_or(&member.span);
        let kind = match problem.kind {
            ProblemKind::UnsupportedParameter => ExceptionName::UnsupportedParameter,
            ProblemKind::SourceResolutionGap => ExceptionName::UnsupportedParameter,
        };
        let kind_name = match problem.kind {
            ProblemKind::UnsupportedParameter => "UnsupportedParameter",
            ProblemKind::SourceResolutionGap => "source_resolution_gap",
        };
        let coverage_id = stable_id(
            "COVERAGE",
            &[
                Part::Text(&problem.path),
                Part::Number(number(span.line)),
                Part::Text(kind_name),
                Part::Text(&problem.message),
            ],
        );
        if self.gaps.contains_key(&coverage_id) {
            return Ok(());
        }
        self.work.text(file.first_line.as_deref().unwrap_or(""))?;
        let cited = self.gap_cite(file, span);
        let (mut id, mut gap) = crate::records::gap(
            &problem.path,
            span.line,
            kind,
            &problem.message,
            Some(cited),
        );
        if problem.kind == ProblemKind::SourceResolutionGap {
            id = coverage_id;
            gap.id = archkeel_facts::ids::FactId::new(id.clone());
            let data = match gap.data {
                archkeel_facts::sections::GapFact::ExceptionGap { mut data, .. } => {
                    data.module = Some(archkeel_facts::ids::ModuleName::new(&file.module));
                    data.resolution_dimension =
                        Some(archkeel_facts::vocab::ResolutionDimension::Signature);
                    data
                }
                archkeel_facts::sections::GapFact::CollectionGap(_)
                | archkeel_facts::sections::GapFact::SourceResolutionGap(_)
                | archkeel_facts::sections::GapFact::DynamicImportLimit(_)
                | archkeel_facts::sections::GapFact::PrivateAttributeAccessLimit(_) => {
                    return Err(Stop::Input)
                }
            };
            gap.data = archkeel_facts::sections::GapFact::SourceResolutionGap(data);
            gap.subjects = vec![file.module.clone()];
            gap.fact_ids = vec![archkeel_facts::ids::FactId::new(identity)];
        }
        self.gaps.entry(id).or_insert(gap);
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    fn attribute(
        &mut self,
        file: &File,
        span: &Span,
        parent: &str,
        name: &str,
        annotation: Option<String>,
        r#static: bool,
        constant: Option<String>,
        visibility: Visibility,
    ) -> Result<Attribute, Stop> {
        self.work.text(parent)?;
        self.work.text(name)?;
        self.work.copies(span)?;
        let id = stable_id(
            "DARTATTR",
            &[
                Part::Text(&file.rel),
                Part::Number(number(span.start_byte)),
                Part::Text(parent),
                Part::Text(name),
            ],
        );
        let qualified = format!("{parent}.{name}");
        self.index(file, span, &id, Some(&qualified));
        Ok(Attribute {
            name: name.to_owned(),
            annotation,
            visibility: VisibilityDetail {
                kind: visibility,
                basis: "language",
                spelling: name.to_owned(),
            },
            definition_id: archkeel_facts::ids::FactId::new(id),
            evidence_ids: vec![archkeel_facts::ids::EvidenceId::new(self.cite(file, span))],
            r#static,
            constant,
        })
    }
}
