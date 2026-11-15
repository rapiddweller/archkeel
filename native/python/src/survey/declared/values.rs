// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module values that one plain statement binds (AD-520, rule 8): a constant
//! (`NAME = 1`) and a type alias (`NAME: TypeAlias = other`). Release 4.0.1 admits these two as
//! `static_constant` and `type_alias`; any other value (a call, a container, a name) is a
//! binding with no proof of its kind, so it has no record here.

use archkeel_facts::data::ValueData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, EvidenceClass, SymbolCategory};
use archkeel_facts::{Record, SymbolFact};
use ruff_python_ast::{Expr, Stmt};
use ruff_text_size::Ranged;

use super::kind::{imported, Reading};
use super::reader::Unwritable;
use super::Writer;
use crate::survey::bound::Bound;

/// The value of an `ast.Constant`.
fn constant(value: &Expr) -> bool {
    matches!(
        value,
        Expr::StringLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::NoneLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::EllipsisLiteral(_)
    )
}

/// The names of an admitted assignment, its category (`None`: a constant) and its alias text.
type Admitted<'s> = (Vec<&'s str>, Option<SymbolCategory>, Option<String>);

fn plain_name(target: &Expr) -> Option<&str> {
    match target {
        Expr::Name(name) => Some(name.id.as_str()),
        _ => None,
    }
}

/// The annotation is `TypeAlias` of `typing`, read through its one plain import.
fn type_alias(annotation: &Expr, reading: &Reading<'_>) -> bool {
    imported(annotation, reading).is_some_and(|(module, symbol)| {
        matches!(module.as_str(), "typing" | "typing_extensions") && symbol == "TypeAlias"
    })
}

impl Writer<'_, '_> {
    /// The records of one module-body assignment: one for each of its names that it binds alone.
    pub(super) fn value(
        &mut self,
        statement: &Stmt,
        bound: &Bound,
        reading: &Reading<'_>,
    ) -> Result<(), Unwritable> {
        let start = statement.range().start();
        let Some((names, category, alias)) = self.admitted(statement, reading) else {
            return Ok(());
        };
        for name in names.into_iter().filter(|name| bound.sole(name, start)) {
            self.value_record(statement, name, category, alias.clone());
        }
        Ok(())
    }

    /// The names of an assignment that 4.0.1 admits, with the category and the alias text.
    fn admitted<'s>(&self, statement: &'s Stmt, reading: &Reading<'_>) -> Option<Admitted<'s>> {
        match statement {
            Stmt::Assign(node) if constant(&node.value) => {
                let names: Vec<&str> = node.targets.iter().filter_map(plain_name).collect();
                (names.len() == node.targets.len()).then_some((names, None, None))
            }
            Stmt::AnnAssign(node) => {
                let name = plain_name(&node.target)?;
                let value = node.value.as_deref()?;
                if !type_alias(&node.annotation, reading) {
                    return constant(value).then(|| (vec![name], None, None));
                }
                let text = self.scan.text(Some(value)).ok().flatten()?;
                Some((vec![name], Some(SymbolCategory::TypeAlias), Some(text)))
            }
            _ => None,
        }
    }

    fn value_record(
        &mut self,
        statement: &Stmt,
        name: &str,
        category: Option<SymbolCategory>,
        alias: Option<String>,
    ) {
        let module = self.scan.module;
        let qualname = format!("{}.{name}", module.name);
        let header = self.header(name, &module.name, None);
        let mut data = ValueData::declared(header, category);
        data.alias = alias;
        let fact = match category {
            Some(_) => SymbolFact::TypeAlias(data),
            None => SymbolFact::StaticConstant(data),
        };
        let crate::module::Location { line, column, .. } = module.location(statement);
        let id = stable_id(
            "SYM",
            &[
                Part::Text(&qualname),
                Part::Text(&module.rel),
                Part::Number(line),
                Part::Number(column),
            ],
        );
        let evidence = self.scan.evidence(statement);
        let mut subjects = vec![qualname, module.name.clone()];
        subjects.sort();
        self.out.push(Record {
            id: FactId::new(id),
            evidence_class: EvidenceClass::Fact,
            area: Area::RepositoryTopology,
            title: name.to_owned(),
            subjects,
            evidence_ids: vec![EvidenceId::new(evidence)],
            fact_ids: Vec::new(),
            data: fact,
        });
    }
}
