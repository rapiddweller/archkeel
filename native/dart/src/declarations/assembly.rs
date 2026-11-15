// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The state of the declaration assembly and the helpers that its passes share. This is the leaf
//! of `declarations`: the passes call it and it calls none of them.

use super::types::{
    Category, Data, Detail, File, Kind, Location, Parameter, ParameterKind, Scope, Symbol,
    VisibilityDetail,
};
use super::work::{Stop, Work};
use crate::syntax::{ParameterKind as SyntaxParameterKind, Span};
use archkeel_facts::envelope::Evidence;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::sections::GapFact;
use archkeel_facts::vocab::ExceptionName;
use archkeel_facts::Record;
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Default, Serialize)]
pub(crate) struct Output {
    pub(crate) symbols: Vec<Symbol>,
    pub(super) evidence: Vec<Evidence>,
    pub(super) gaps: Vec<Record<GapFact>>,
    pub(super) definition_ids: Vec<((String, usize, usize), String)>,
    pub(super) definition_names: Vec<((String, usize), String)>,
    pub(crate) scope_candidates: Vec<Scope>,
    pub(super) symbol_by_name: Vec<(String, String)>,
    pub(super) incomplete_inventory_ids: Vec<String>,
    pub(super) work: usize,
}

#[derive(Default)]
pub(crate) struct Assembly {
    pub(crate) output: Output,
    pub(crate) evidence: BTreeMap<String, Evidence>,
    pub(crate) gaps: BTreeMap<String, Record<GapFact>>,
    pub(crate) ids: BTreeMap<(String, usize, usize), String>,
    pub(crate) names: BTreeMap<(String, usize), String>,
    pub(crate) symbols: BTreeMap<String, String>,
    pub(crate) work: Work,
}

impl Assembly {
    pub(crate) fn meta(
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
            base_declarations: None,
            modifiers: None,
            detail: Detail::Value {
                annotation: None,
                constant: None,
            },
        })
    }

    pub(super) fn parameters(
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

    pub(crate) fn index(&mut self, file: &File, span: &Span, id: &str, qualified: Option<&str>) {
        self.ids
            .insert((file.rel.clone(), span.line, span.column), id.to_owned());
        if let Some(qualified) = qualified {
            self.names
                .insert((file.rel.clone(), span.start_byte), qualified.to_owned());
        }
    }

    pub(crate) fn cite(&mut self, file: &File, span: &Span) -> String {
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

    pub(super) fn gap(&mut self, file: &File, span: &Span, kind: ExceptionName, message: &str) {
        let (id, _) = crate::records::gap(&file.rel, span.line, kind, message, None);
        if self.gaps.contains_key(&id) {
            return;
        }
        let cited = self.gap_cite(file, span);
        let (id, gap) = crate::records::gap(&file.rel, span.line, kind, message, Some(cited));
        self.gaps.entry(id).or_insert(gap);
    }

    pub(crate) fn gap_cite(&mut self, file: &File, span: &Span) -> String {
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

    pub(crate) fn publish(&mut self, file: &File, span: &Span, id: String, kind: Kind, data: Data) {
        let qualified = data.qualified_name.clone();
        let cited = self.cite(file, span);
        self.symbols.insert(qualified.clone(), id.clone());
        self.output.symbols.push(Symbol::new(
            id,
            kind,
            format!("{qualified} declaration"),
            vec![qualified],
            vec![archkeel_facts::ids::EvidenceId::new(cited)],
            data,
            archkeel_facts::vocab::Area::Source,
        ));
    }
}

pub(super) fn parameter_kind(kind: SyntaxParameterKind) -> ParameterKind {
    match kind {
        SyntaxParameterKind::Named => ParameterKind::KeywordOnly,
        SyntaxParameterKind::Positional => ParameterKind::Positional,
    }
}

pub(super) fn number(value: usize) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}

pub(super) fn identity(rel: &str, span: &Span, qualified: &str, kind: &str) -> String {
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
