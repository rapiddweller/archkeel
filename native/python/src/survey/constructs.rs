// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Written constructs with lexical owners (AD-658, AD-666, AD-680, AD-682, AD-684, AD-686).

use archkeel_facts::data::{ConstructData, PlainConstructData, SignalData};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::sections::SignalFact;
use archkeel_facts::vocab::{Area, ConstructForm, EvidenceClass, Signal};
use archkeel_facts::{ConstructFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{CmpOp, ExceptHandler, Expr, Parameter, Stmt};
use ruff_text_size::Ranged;

use super::binders::Binders;
use crate::module::{EvidenceMap, Location, Module};

pub(super) fn collect(
    modules: &[Module],
    binders: &[Binders],
    evidence: &mut EvidenceMap,
) -> Findings {
    let mut records = Vec::new();
    let mut signals = Vec::new();
    let mut complete = true;
    let mut dict_complete = true;
    let mut vars_complete = true;
    let mut compare_complete = true;
    let mut getattr_complete = true;
    for (module, binders) in modules.iter().zip(binders) {
        let found = one(module, binders, evidence);
        records.extend(found.records);
        signals.extend(found.signals);
        complete &= found.broad_complete;
        dict_complete &= found.dict_complete;
        vars_complete &= found.vars_complete;
        compare_complete &= found.compare_complete;
        getattr_complete &= found.getattr_complete;
    }
    Findings {
        records,
        signals,
        broad_complete: complete,
        dict_complete,
        vars_complete,
        compare_complete,
        getattr_complete,
    }
}

pub(super) struct Findings {
    pub records: Vec<Record<ConstructFact>>,
    pub signals: Vec<Record<SignalFact>>,
    pub broad_complete: bool,
    pub dict_complete: bool,
    pub vars_complete: bool,
    pub compare_complete: bool,
    pub getattr_complete: bool,
}

fn one(module: &Module, binders: &Binders, evidence: &mut EvidenceMap) -> Findings {
    let mut walk = Walk {
        module,
        binders,
        evidence,
        owner: module.name.clone(),
        records: Vec::new(),
        signals: Vec::new(),
        complete: true,
        dict_complete: true,
        vars_complete: true,
        compare_complete: true,
        getattr_complete: true,
    };
    walk.visit_body(&module.tree.body);
    Findings {
        records: walk.records,
        signals: walk.signals,
        broad_complete: walk.complete,
        dict_complete: walk.dict_complete,
        vars_complete: walk.vars_complete,
        compare_complete: walk.compare_complete,
        getattr_complete: walk.getattr_complete,
    }
}

struct Walk<'a> {
    module: &'a Module,
    binders: &'a Binders,
    evidence: &'a mut EvidenceMap,
    owner: String,
    records: Vec<Record<ConstructFact>>,
    signals: Vec<Record<SignalFact>>,
    complete: bool,
    dict_complete: bool,
    vars_complete: bool,
    compare_complete: bool,
    getattr_complete: bool,
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
        match stmt {
            Stmt::FunctionDef(node) => {
                if let Some(annotation) = &node.returns {
                    self.annotation(annotation);
                }
            }
            Stmt::AnnAssign(node) => self.annotation(&node.annotation),
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
        self.owner.truncate(length);
    }

    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        if let Some(annotation) = &parameter.annotation {
            let length = self.owner.len();
            self.owner.push(':');
            self.owner.push_str(parameter.name.as_str());
            self.annotation(annotation);
            self.owner.truncate(length);
        }
        visitor::walk_parameter(self, parameter);
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
        if matches!(expr, Expr::Name(name) if name.id.as_str() == "getattr") {
            self.getattr_complete = false;
        }
        if let Expr::Call(call) = expr {
            self.call(expr, call);
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
    fn annotation(&mut self, annotation: &Expr) {
        struct Any(bool);
        impl<'a> Visitor<'a> for Any {
            fn visit_expr(&mut self, expr: &'a Expr) {
                self.0 |= matches!(expr, Expr::Name(name) if name.id.as_str() == "Any")
                    || matches!(expr, Expr::Attribute(attr) if attr.attr.as_str() == "Any");
                visitor::walk_expr(self, expr);
            }
        }
        let mut found = Any(false);
        found.visit_expr(annotation);
        if !found.0 {
            return;
        }
        let text = &self.module.text()[annotation.start().to_usize()..annotation.end().to_usize()];
        self.signal(
            annotation,
            "any_annotation",
            "any_annotation",
            SignalFact::AnyAnnotation(self.signal_data(Signal::AnyAnnotation, Some(text))),
        );
    }

    fn call(&mut self, expr: &Expr, call: &ruff_python_ast::ExprCall) {
        self.dict_complete = false;
        self.compare_complete = false;
        let known = matches!(&*call.func, Expr::Name(name)
            if name.id.as_str() == "vars" && self.binders.builtin_visible("vars"));
        if known {
            self.construct(expr, "vars_call", "vars", ConstructFact::VarsCall);
        } else {
            self.vars_complete = false;
        }
        let known_getattr = matches!(&*call.func, Expr::Name(name)
            if name.id.as_str() == "getattr" && self.binders.builtin_visible("getattr"));
        if known_getattr {
            self.getattr(expr);
        } else {
            self.getattr_complete = false;
        }
    }

    fn getattr(&mut self, node: &impl Ranged) {
        self.signal(
            node,
            "getattr_call",
            "getattr",
            SignalFact::GetattrCall(self.signal_data(Signal::GetattrCall, None)),
        );
    }

    fn signal_data(&self, signal: Signal, annotation: Option<&str>) -> SignalData {
        SignalData {
            annotation: annotation.map(str::to_owned),
            expression: None,
            line: None,
            owner: self.owner.clone(),
            positions: None,
            qualified_name: None,
            signal,
            statement: None,
            tag: None,
        }
    }

    fn signal(&mut self, node: &impl Ranged, kind: &str, name: &str, data: SignalFact) {
        let place = self.module.location(node);
        let evidence = self.module.evidence(self.evidence, node);
        let id = self.site_id("TYPE", &place, kind);
        let record = self.make(id, evidence, name, Area::TypeArchitecture, data);
        self.signals.push(record);
    }

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
        let id = self.site_id("CONSTRUCT", &place, kind);
        let record = self.make(id, evidence, name, Area::Constructs, data);
        self.records.push(record);
    }

    fn site_id(&self, prefix: &str, place: &Location, kind: &str) -> String {
        stable_id(
            prefix,
            &[
                Part::Text(&self.module.rel),
                Part::Number(place.line),
                Part::Number(place.column),
                Part::Text(kind),
            ],
        )
    }

    fn make<D>(&self, id: String, evidence: String, name: &str, area: Area, data: D) -> Record<D> {
        Record {
            id: FactId::new(id),
            evidence_class: EvidenceClass::Fact,
            area,
            title: format!("{} uses {name}", self.owner),
            subjects: vec![self.owner.clone()],
            evidence_ids: vec![EvidenceId::new(evidence)],
            fact_ids: Vec::new(),
            data,
        }
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
