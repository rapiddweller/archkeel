// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Written assert statements and their lexical owners (AD-658).

use archkeel_facts::data::PlainConstructData;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{ConstructFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::Stmt;

use crate::module::{EvidenceMap, Module};

pub(super) fn asserts(module: &Module, evidence: &mut EvidenceMap) -> Vec<Record<ConstructFact>> {
    let mut walk = Walk {
        module,
        evidence,
        owner: module.name.clone(),
        records: Vec::new(),
    };
    walk.visit_body(&module.tree.body);
    walk.records
}

struct Walk<'a> {
    module: &'a Module,
    evidence: &'a mut EvidenceMap,
    owner: String,
    records: Vec<Record<ConstructFact>>,
}

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if matches!(stmt, Stmt::Assert(_)) {
            let place = self.module.location(stmt);
            let id = stable_id(
                "CONSTRUCT",
                &[
                    Part::Text(&self.module.rel),
                    Part::Number(place.line),
                    Part::Number(place.column),
                    Part::Text("assert_statement"),
                ],
            );
            let evidence = self.module.evidence(self.evidence, stmt);
            self.records.push(Record {
                id: FactId::new(id),
                evidence_class: EvidenceClass::Fact,
                area: Area::Constructs,
                title: format!("{} uses assert", self.owner),
                subjects: vec![self.owner.clone()],
                evidence_ids: vec![EvidenceId::new(evidence)],
                fact_ids: Vec::new(),
                data: ConstructFact::AssertStatement(PlainConstructData {
                    construct: "assert".to_owned(),
                    owner: self.owner.clone(),
                }),
            });
        }
        let name = match stmt {
            Stmt::FunctionDef(node) => Some(node.name.as_str()),
            Stmt::ClassDef(node) => Some(node.name.as_str()),
            _ => None,
        };
        let length = self.owner.len();
        if let Some(name) = name {
            self.owner.push('.');
            self.owner.push_str(name);
        }
        visitor::walk_stmt(self, stmt);
        self.owner.truncate(length);
    }
}
