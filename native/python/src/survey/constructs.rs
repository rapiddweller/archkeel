// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Written constructs with lexical owners (AD-658, AD-666, AD-680, AD-682, AD-684, AD-686).

use archkeel_facts::data::{ConstructData, PlainConstructData, SignalData};
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::sections::SignalFact;
use archkeel_facts::vocab::{Area, ConstructForm, EvidenceClass, Signal};
use archkeel_facts::{ConstructFact, ImportFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{CmpOp, ExceptHandler, Expr, Parameter, Stmt};
use ruff_text_size::Ranged;
use std::collections::HashSet;

use super::binders::Binders;
use super::support::{Construct, Support};
use crate::module::{EvidenceMap, Location, Module};

#[path = "constructs_ignores.rs"]
mod ignores;
#[path = "constructs_placeholder.rs"]
mod placeholder;

pub(super) fn collect(
    modules: &[Module],
    binders: &[Binders],
    imports: &[Record<ImportFact>],
    sets: (&HashSet<String>, &HashSet<String>),
    evidence: &mut EvidenceMap,
) -> Findings {
    let mut records = Vec::new();
    let mut signals = Vec::new();
    let mut support = Support::start();
    let by_module = super::declared::placeholder::by_module(imports);
    for (module, binders) in modules.iter().zip(binders) {
        let source_imports = by_module
            .get(module.name.as_str())
            .map_or(&[][..], Vec::as_slice);
        let withheld =
            super::declared::placeholder::withheld(module, binders, source_imports, sets);
        let mut found = one(module, binders, evidence);
        found
            .records
            .extend(placeholder::collect(module, evidence, &withheld));
        records.extend(found.records);
        signals.extend(found.signals);
        support.meet(&found.support);
    }
    Findings {
        records,
        signals,
        support,
    }
}

pub(super) struct Findings {
    pub records: Vec<Record<ConstructFact>>,
    pub signals: Vec<Record<SignalFact>>,
    /// What the survey sees of each construct (AD-737).
    pub support: Support,
}

fn one(module: &Module, binders: &Binders, evidence: &mut EvidenceMap) -> Findings {
    let unique = binders.unique();
    let mut loaders = HashSet::new();
    let mut importlibs = HashSet::new();
    let mut casts = HashSet::new();
    let mut typing_modules = HashSet::new();
    for stmt in &module.tree.body {
        let (aliases, wanted, target) = match stmt {
            Stmt::ImportFrom(node)
                if node.level == 0
                    && node
                        .module
                        .as_ref()
                        .is_some_and(|name| name.as_str() == "importlib") =>
            {
                (&node.names, "import_module", &mut loaders)
            }
            Stmt::ImportFrom(node)
                if node.level == 0
                    && node.module.as_ref().is_some_and(|name| {
                        matches!(name.as_str(), "typing" | "typing_extensions")
                    }) =>
            {
                (&node.names, "cast", &mut casts)
            }
            Stmt::Import(node) => (&node.names, "importlib", &mut importlibs),
            _ => continue,
        };
        for alias in aliases {
            let name = alias.asname.as_ref().unwrap_or(&alias.name).as_str();
            if alias.name.as_str() == wanted && unique.contains(name) {
                target.insert(name.to_owned());
            }
        }
        let Stmt::Import(node) = stmt else {
            continue;
        };
        for alias in &node.names {
            let name = alias.asname.as_ref().unwrap_or(&alias.name).as_str();
            if matches!(alias.name.as_str(), "typing" | "typing_extensions")
                && unique.contains(name)
            {
                typing_modules.insert(name.to_owned());
            }
        }
    }
    let mut walk = Walk {
        module,
        binders,
        evidence,
        owner: module.name.clone(),
        records: Vec::new(),
        signals: Vec::new(),
        support: Support::start(),
        loaders,
        importlibs,
        casts,
        typing_modules,
        comments: ignores::Comments::new(module.text(), crate::parse::comments(module.text())),
    };
    walk.visit_body(&module.tree.body);
    if !walk.comments.complete() {
        walk.support.downgrade(Construct::TypeIgnore);
    }
    Findings {
        records: walk.records,
        signals: walk.signals,
        support: walk.support,
    }
}

struct Walk<'a> {
    module: &'a Module,
    binders: &'a Binders,
    evidence: &'a mut EvidenceMap,
    owner: String,
    records: Vec<Record<ConstructFact>>,
    signals: Vec<Record<SignalFact>>,
    support: Support,
    loaders: HashSet<String>,
    importlibs: HashSet<String>,
    casts: HashSet<String>,
    typing_modules: HashSet<String>,
    comments: ignores::Comments,
}

impl<'a> Visitor<'a> for Walk<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if matches!(stmt, Stmt::Match(_)) {
            self.support.downgrade(Construct::StringLiteralCompare);
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
            Stmt::Expr(node) if ignores::member_call(&node.value) => self.type_ignore(stmt),
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
            self.support.downgrade(Construct::BroadExcept);
        }
        visitor::walk_except_handler(self, handler);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if matches!(expr, Expr::Name(name) if name.id.as_str() == "vars") {
            self.support.downgrade(Construct::Vars);
        }
        if matches!(expr, Expr::Name(name) if name.id.as_str() == "getattr") {
            self.support.downgrade(Construct::Getattr);
        }
        if let Expr::Call(call) = expr {
            self.call(expr, call);
        }
        if let Expr::Compare(node) = expr {
            self.support.downgrade(Construct::StringLiteralCompare);
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
                self.support.downgrade(Construct::StringLiteralCompare);
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

fn named_call(func: &Expr, names: &HashSet<String>, modules: &HashSet<String>, attr: &str) -> bool {
    match func {
        Expr::Name(name) => names.contains(name.id.as_str()),
        Expr::Attribute(node) => {
            node.attr.as_str() == attr
                && matches!(&*node.value, Expr::Name(name) if modules.contains(name.id.as_str()))
        }
        _ => false,
    }
}

impl Walk<'_> {
    fn type_ignore(&mut self, stmt: &Stmt) {
        let start = stmt.start().to_usize();
        let end = stmt.end().to_usize();
        let location = self.module.location(stmt);
        let Ok(column) = usize::try_from(location.column) else {
            return;
        };
        let Some((tag, text)) = self
            .comments
            .take(self.module.text(), start - column, start, end)
        else {
            return;
        };
        let data = ignores::data(&self.owner, location.line, tag, text);
        self.signal(
            stmt,
            "type_ignore",
            "type_ignore",
            SignalFact::TypeIgnore(data),
        );
    }

    fn annotation(&mut self, annotation: &Expr) {
        // A name `Any` that the module binds to another object is not `typing.Any` (AD-874).
        struct Any<'b>(&'b Binders, bool);
        impl<'a> Visitor<'a> for Any<'_> {
            fn visit_expr(&mut self, expr: &'a Expr) {
                self.1 |= matches!(expr, Expr::Name(name) if name.id.as_str() == "Any" && !self.0.any_is_local())
                    || matches!(expr, Expr::Attribute(attr) if attr.attr.as_str() == "Any");
                visitor::walk_expr(self, expr);
            }
        }
        let mut found = Any(self.binders, false);
        found.visit_expr(annotation);
        if !found.1 {
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
        self.support.downgrade(Construct::DunderDict);
        self.support.downgrade(Construct::StringLiteralCompare);
        let loader = matches!(&*call.func, Expr::Name(name)
            if name.id.as_str() == "__import__" && self.binders.builtin_visible("__import__"))
            || named_call(&call.func, &self.loaders, &self.importlibs, "import_module");
        if loader {
            self.call_signal(
                expr,
                &call.func,
                "dynamic_import",
                "dynamic_import",
                Signal::DynamicImport,
                SignalFact::DynamicImport,
            );
        }
        if named_call(&call.func, &self.casts, &self.typing_modules, "cast") {
            self.call_signal(
                expr,
                &call.func,
                "cast_call",
                "cast",
                Signal::CastCall,
                SignalFact::CastCall,
            );
        }
        let known = matches!(&*call.func, Expr::Name(name)
            if name.id.as_str() == "vars" && self.binders.builtin_visible("vars"));
        if known {
            self.construct(expr, "vars_call", "vars", ConstructFact::VarsCall);
        } else {
            self.support.downgrade(Construct::Vars);
        }
        let known_getattr = matches!(&*call.func, Expr::Name(name)
            if name.id.as_str() == "getattr" && self.binders.builtin_visible("getattr"));
        if known_getattr {
            self.getattr(expr);
        } else {
            self.support.downgrade(Construct::Getattr);
        }
    }

    fn call_signal(
        &mut self,
        expr: &Expr,
        func: &Expr,
        kind: &str,
        name: &str,
        signal: Signal,
        fact: fn(SignalData) -> SignalFact,
    ) {
        let mut data = self.signal_data(signal, None);
        data.expression =
            Some(self.module.text()[func.start().to_usize()..func.end().to_usize()].to_owned());
        self.signal(expr, kind, name, fact(data));
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
