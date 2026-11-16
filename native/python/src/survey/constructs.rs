// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Written asserts, broad exception handlers and `__dict__` reads (AD-658, AD-666, AD-680).

use archkeel_facts::data::{ConstructData, PlainConstructData};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{ConstructFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{ExceptHandler, Expr, Stmt};

use super::binders::Binders;
use crate::module::{EvidenceMap, Location, Module};

pub(super) fn collect(
    modules: &[Module],
    binders: &[Binders],
    evidence: &mut EvidenceMap,
) -> (Vec<Record<ConstructFact>>, bool, bool) {
    let mut records = Vec::new();
    let mut complete = true;
    let mut dict_complete = true;
    for (module, binders) in modules.iter().zip(binders) {
        let (found, read, dict_read) = one(module, binders, evidence);
        records.extend(found);
        complete &= read;
        dict_complete &= dict_read;
    }
    (records, complete, dict_complete)
}

fn one(
    module: &Module,
    binders: &Binders,
    evidence: &mut EvidenceMap,
) -> (Vec<Record<ConstructFact>>, bool, bool) {
    let mut walk = Walk {
        module,
        binders,
        evidence,
        owner: module.name.clone(),
        records: Vec::new(),
        complete: true,
        dict_complete: true,
    };
    walk.visit_body(&module.tree.body);
    (walk.records, walk.complete, walk.dict_complete)
}

struct Walk<'a> {
    module: &'a Module,
    binders: &'a Binders,
    evidence: &'a mut EvidenceMap,
    owner: String,
    records: Vec<Record<ConstructFact>>,
    complete: bool,
    dict_complete: bool,
}

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if matches!(stmt, Stmt::Assert(_)) {
            let place = self.module.location(stmt);
            let evidence = self.module.evidence(self.evidence, stmt);
            self.record(
                place,
                evidence,
                "assert_statement",
                "assert",
                ConstructFact::AssertStatement(PlainConstructData {
                    construct: "assert".to_owned(),
                    owner: self.owner.clone(),
                }),
            );
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

    fn visit_except_handler(&mut self, handler: &'a ExceptHandler) {
        let ExceptHandler::ExceptHandler(node) = handler;
        let broad = node.type_.as_deref().is_none_or(|expr| self.broad(expr));
        if broad {
            let place = self.module.location(handler);
            let evidence = self.module.evidence(self.evidence, handler);
            self.record(
                place,
                evidence,
                "broad_except",
                "broad_except",
                ConstructFact::BroadExcept(ConstructData {
                    construct: "broad_except".to_owned(),
                    form: None,
                    handled: None,
                    owner: self.owner.clone(),
                }),
            );
        } else {
            self.complete = false;
        }
        visitor::walk_except_handler(self, handler);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if matches!(expr, Expr::Call(_)) {
            self.dict_complete = false;
        }
        if let Expr::Attribute(node) = expr {
            if node.attr.as_str() == "__dict__" {
                let place = self.module.location(&node.attr);
                let evidence = self.module.evidence(self.evidence, &node.attr);
                self.record(
                    place,
                    evidence,
                    "dunder_dict",
                    "dunder_dict",
                    ConstructFact::DunderDict(PlainConstructData {
                        construct: "dunder_dict".to_owned(),
                        owner: self.owner.clone(),
                    }),
                );
            }
        }
        visitor::walk_expr(self, expr);
    }
}

impl Walk<'_> {
    fn record(
        &mut self,
        place: Location,
        evidence: String,
        kind: &str,
        name: &str,
        data: ConstructFact,
    ) {
        let id = stable_id(
            "CONSTRUCT",
            &[
                Part::Text(&self.module.rel),
                Part::Number(place.line),
                Part::Number(place.column),
                Part::Text(kind),
            ],
        );
        self.records.push(Record {
            id: FactId::new(id),
            evidence_class: EvidenceClass::Fact,
            area: Area::Constructs,
            title: format!("{} uses {name}", self.owner),
            subjects: vec![self.owner.clone()],
            evidence_ids: vec![EvidenceId::new(evidence)],
            fact_ids: Vec::new(),
            data,
        });
    }

    fn broad(&self, expr: &Expr) -> bool {
        match expr {
            Expr::Name(name) => {
                matches!(name.id.as_str(), "Exception" | "BaseException")
                    && self.binders.builtin_visible(name.id.as_str())
            }
            Expr::Tuple(tuple) => tuple.elts.iter().any(|item| self.broad(item)),
            _ => false,
        }
    }
}
