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
use ruff_python_ast::{Expr, Stmt, StmtFunctionDef};
use ruff_text_size::{Ranged, TextSize};
use std::collections::HashMap;

use crate::module::{EvidenceMap, Module};
use crate::survey::support::{PlaceholderCoverage as Coverage, PlaceholderDecision as Decision};

pub(super) fn collect(
    module: &Module,
    evidence: &mut EvidenceMap,
    decisions: &HashMap<TextSize, Decision>,
) -> (Vec<Record<ConstructFact>>, Coverage) {
    if module.rel.ends_with(".pyi") {
        return (Vec::new(), Coverage::Complete);
    }
    let mut walk = Placeholders {
        module,
        evidence,
        decisions,
        coverage: Coverage::Complete,
        owner: module.name.clone(),
        found: Vec::new(),
    };
    walk.visit_body(&module.tree.body);
    (walk.found, walk.coverage)
}

struct Placeholders<'a> {
    module: &'a Module,
    evidence: &'a mut EvidenceMap,
    decisions: &'a HashMap<TextSize, Decision>,
    coverage: Coverage,
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
            self.body(node, stmt);
        }
        visitor::walk_stmt(self, stmt);
        self.owner.truncate(length);
    }
}

impl Placeholders<'_> {
    fn body(&mut self, node: &StmtFunctionDef, stmt: &Stmt) {
        let doc = |stmt: &Stmt| matches!(stmt, Stmt::Expr(expr) if matches!(&*expr.value, Expr::StringLiteral(_)));
        let empty = |stmt: &Stmt| {
            matches!(stmt, Stmt::Pass(_))
                || matches!(stmt, Stmt::Expr(expr) if matches!(&*expr.value, Expr::EllipsisLiteral(_)))
        };
        let statement = match node.body.as_slice() {
            [only] => Some((only, true)),
            [first, second] if doc(first) => Some((second, false)),
            _ => None,
        };
        if let Some((statement, only)) = statement {
            let empty = empty(statement) || (only && doc(statement));
            match (empty, self.decisions.get(&node.start()), self.coverage) {
                (true, Some(Decision::Declaration), Coverage::Complete) => {
                    self.coverage = Coverage::UsesProtocol;
                }
                (true, Some(Decision::Declaration), _) => {}
                (true, Some(Decision::Unread), _) => self.coverage = Coverage::Incomplete,
                (true, None, _) => self.record(stmt),
                (false, _, _) if matches!(statement, Stmt::Raise(_)) => {
                    self.coverage = Coverage::Incomplete;
                }
                (false, _, _) => {}
            }
        }
    }

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
