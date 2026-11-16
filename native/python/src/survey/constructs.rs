// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Written constructs with lexical owners (AD-658, AD-666, AD-680, AD-682, AD-684).

use archkeel_facts::data::{ConstructData, PlainConstructData};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, ConstructForm, EvidenceClass};
use archkeel_facts::{ConstructFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{CmpOp, ExceptHandler, Expr, Stmt};
use ruff_text_size::Ranged;

use super::binders::Binders;
use crate::module::{EvidenceMap, Location, Module};

pub(super) fn collect(
    modules: &[Module],
    binders: &[Binders],
    evidence: &mut EvidenceMap,
) -> (Vec<Record<ConstructFact>>, bool, bool, bool, bool) {
    let mut records = Vec::new();
    let mut complete = true;
    let mut dict_complete = true;
    let mut vars_complete = true;
    let mut compare_complete = true;
    for (module, binders) in modules.iter().zip(binders) {
        let (found, read, dict_read, vars_read, compare_read) = one(module, binders, evidence);
        records.extend(found);
        complete &= read;
        dict_complete &= dict_read;
        vars_complete &= vars_read;
        compare_complete &= compare_read;
    }
    (
        records,
        complete,
        dict_complete,
        vars_complete,
        compare_complete,
    )
}

fn one(
    module: &Module,
    binders: &Binders,
    evidence: &mut EvidenceMap,
) -> (Vec<Record<ConstructFact>>, bool, bool, bool, bool) {
    let mut walk = Walk {
        module,
        binders,
        evidence,
        owner: module.name.clone(),
        records: Vec::new(),
        complete: true,
        dict_complete: true,
        vars_complete: true,
        compare_complete: true,
    };
    walk.visit_body(&module.tree.body);
    (
        walk.records,
        walk.complete,
        walk.dict_complete,
        walk.vars_complete,
        walk.compare_complete,
    )
}

struct Walk<'a> {
    module: &'a Module,
    binders: &'a Binders,
    evidence: &'a mut EvidenceMap,
    owner: String,
    records: Vec<Record<ConstructFact>>,
    complete: bool,
    dict_complete: bool,
    vars_complete: bool,
    compare_complete: bool,
}

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if matches!(stmt, Stmt::Match(_)) {
            self.compare_complete = false;
        }
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
            self.construct(
                handler,
                "broad_except",
                "broad_except",
                ConstructFact::BroadExcept,
            );
        } else {
            self.complete = false;
        }
        visitor::walk_except_handler(self, handler);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if matches!(expr, Expr::Name(name) if name.id.as_str() == "vars") {
            self.vars_complete = false;
        }
        if let Expr::Call(call) = expr {
            self.dict_complete = false;
            self.compare_complete = false;
            let known = matches!(&*call.func, Expr::Name(name)
                if name.id.as_str() == "vars" && self.binders.builtin_visible("vars"));
            if known {
                self.construct(expr, "vars_call", "vars", ConstructFact::VarsCall);
            } else {
                self.vars_complete = false;
            }
        }
        if let Expr::Compare(node) = expr {
            self.compare_complete = false;
            let literal =
                |value: &Expr| matches!(value, Expr::StringLiteral(_) | Expr::BytesLiteral(_));
            let found = node
                .ops
                .iter()
                .zip(node.operands.windows(2))
                .any(|(op, pair)| {
                    matches!(op, CmpOp::Eq | CmpOp::NotEq)
                        && (literal(&pair[0]) || literal(&pair[1]))
                });
            if found {
                let place = self.module.location(expr);
                let evidence = self.module.evidence(self.evidence, expr);
                let mut data = self.data("string_literal_compare");
                data.form = Some(ConstructForm::Compare);
                self.record(
                    place,
                    evidence,
                    "string_literal_compare",
                    "string_literal_compare",
                    ConstructFact::StringLiteralCompare(data),
                );
            }
        }
        if let Expr::Attribute(node) = expr {
            if matches!(
                node.attr.as_str(),
                "startswith" | "endswith" | "__eq__" | "__ne__" | "__contains__"
            ) {
                self.compare_complete = false;
            }
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
    fn construct(
        &mut self,
        node: &impl Ranged,
        kind: &str,
        name: &str,
        fact: fn(ConstructData) -> ConstructFact,
    ) {
        let place = self.module.location(node);
        let evidence = self.module.evidence(self.evidence, node);
        self.record(place, evidence, kind, name, fact(self.data(name)));
    }

    fn data(&self, name: &str) -> ConstructData {
        ConstructData {
            construct: name.to_owned(),
            form: None,
            handled: None,
            owner: self.owner.clone(),
        }
    }

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
