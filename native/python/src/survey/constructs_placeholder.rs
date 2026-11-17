// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The evidence of a written empty function body.

use archkeel_facts::data::PlaceholderData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, EvidenceClass, PlaceholderForm};
use archkeel_facts::{ConstructFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Stmt};
use std::collections::HashSet;

use crate::module::{EvidenceMap, Module};

pub(super) fn collect(
    module: &Module,
    evidence: &mut EvidenceMap,
    withheld: &HashSet<String>,
) -> Vec<Record<ConstructFact>> {
    if module.rel.ends_with(".pyi") {
        return Vec::new();
    }
    let mut walk = Placeholders {
        module,
        evidence,
        withheld,
        owner: module.name.clone(),
        found: Vec::new(),
    };
    walk.visit_body(&module.tree.body);
    walk.found
}

struct Placeholders<'a> {
    module: &'a Module,
    evidence: &'a mut EvidenceMap,
    withheld: &'a HashSet<String>,
    owner: String,
    found: Vec<Record<ConstructFact>>,
}

impl<'a> Visitor<'a> for Placeholders<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let name = match stmt {
            Stmt::ClassDef(node) => Some(&*node.name.id),
            Stmt::FunctionDef(node) => Some(&*node.name.id),
            _ => None,
        };
        let length = str::len(&self.owner);
        if let Some(name) = name {
            self.owner.push('.');
            self.owner.push_str(name);
        }
        if let Stmt::FunctionDef(node) = stmt {
            let doc = |stmt: &Stmt| matches!(stmt, Stmt::Expr(expr) if matches!(&*expr.value, Expr::StringLiteral(_)));
            let empty = |stmt: &Stmt| {
                matches!(stmt, Stmt::Pass(_))
                    || matches!(stmt, Stmt::Expr(expr) if matches!(&*expr.value, Expr::EllipsisLiteral(_)))
            };
            let placeholder = match node.body.as_slice() {
                [only] => empty(only) || doc(only),
                [first, second] => doc(first) && empty(second),
                _ => false,
            };
            if placeholder && !self.withheld.contains(&self.owner) {
                self.record(stmt);
            }
        }
        visitor::walk_stmt(self, stmt);
        self.owner.truncate(length);
    }
}

impl Placeholders<'_> {
    fn record(&mut self, stmt: &Stmt) {
        let place = self.module.location(stmt);
        let evidence = self.module.evidence(self.evidence, stmt);
        let id = stable_id(
            "CONSTRUCT",
            &[
                Part::Text(&self.module.rel),
                Part::Number(place.line),
                Part::Number(place.column),
                Part::Text("placeholder_body"),
            ],
        );
        self.found.push(Record {
            id: FactId::new(id),
            evidence_class: EvidenceClass::Fact,
            area: Area::Constructs,
            title: format!("{} uses placeholder_body", self.owner),
            subjects: vec![self.owner.clone()],
            evidence_ids: vec![EvidenceId::new(evidence)],
            fact_ids: Vec::new(),
            data: ConstructFact::PlaceholderBody(PlaceholderData {
                construct: "placeholder_body".to_owned(),
                form: PlaceholderForm::Empty,
                owner: self.owner.clone(),
            }),
        });
    }
}
