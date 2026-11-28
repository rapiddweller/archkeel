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
use ruff_text_size::{Ranged, TextRange};
use std::collections::HashSet;

use super::binders::{named_call, Binders};
use super::class_writes::ClassWrites;
use super::declared::placeholder as declarations;
use super::support::{Construct, Seen, Support};
use crate::module::{EvidenceMap, Location, Module};

#[path = "constructs_ignores.rs"]
mod ignores;
#[path = "constructs_placeholder.rs"]
mod placeholder;

pub(super) fn collect(
    (modules, binders, imports): (&[Module], &[Binders], &[Record<ImportFact>]),
    sets: (&HashSet<String>, &HashSet<String>),
    (writes, hazard_free, all_inputs_read): (&ClassWrites, bool, bool),
    stdlib: &HashSet<&str>,
    evidence: &mut EvidenceMap,
) -> Findings {
    // AD-880: no site of the scan changes the import system or runs a trojan horse, and no write replaces `typing`.
    let typing_unchanged = hazard_free && writes.typing_unchanged();
    let protocol_unchanged = hazard_free
        && all_inputs_read
        && declarations::standard_protocol(modules, imports, stdlib, writes);
    let mut records = Vec::new();
    let mut signals = Vec::new();
    let mut support = Support::start();
    let by_module = declarations::by_module(imports);
    for (module, binders) in modules.iter().zip(binders) {
        let source_imports = by_module
            .get(module.name.as_str())
            .map_or(&[][..], Vec::as_slice);
        let decisions =
            declarations::decisions(module, binders, source_imports, sets, protocol_unchanged);
        let mut found = one(module, binders, typing_unchanged, evidence);
        let (placeholders, coverage) = placeholder::collect(module, evidence, &decisions);
        found.records.extend(placeholders);
        found.support.observe_placeholder(coverage);
        records.extend(found.records);
        signals.extend(found.signals);
        support.meet(&found.support);
    }
    support.settle();
    if !all_inputs_read {
        support.downgrade(Construct::Placeholder);
    }
    Findings {
        records,
        signals,
        support,
        protocol_unchanged,
    }
}

pub(super) struct Findings {
    pub records: Vec<Record<ConstructFact>>,
    pub signals: Vec<Record<SignalFact>>,
    pub support: Support,
    pub protocol_unchanged: bool,
}

fn one(
    module: &Module,
    binders: &Binders,
    typing_unchanged: bool,
    evidence: &mut EvidenceMap,
) -> Findings {
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
    let mut aliases = Aliases::default();
    for stmt in &module.tree.body {
        aliases.visit_stmt(stmt);
    }
    let mut walk = Walk {
        module,
        binders,
        typing_unchanged,
        evidence,
        owner: module.name.clone(),
        records: Vec::new(),
        signals: Vec::new(),
        support: Support::start(),
        loaders,
        importlibs,
        casts,
        typing_modules,
        aliases,
        consumed: HashSet::new(),
        comments: ignores::Comments::new(module.text(), crate::parse::comments(module.text())),
    };
    walk.hide_by_import();
    walk.visit_body(&module.tree.body);
    if !walk.comments.complete() {
        if let Some(first) = module.tree.body.first() {
            walk.hide(Construct::TypeIgnore, first);
        }
    }
    Findings {
        records: walk.records,
        signals: walk.signals,
        support: walk.support,
        protocol_unchanged: false,
    }
}

/// The builtin functions that a `forbidden_construct` rule can name, with the construct of each.
const BUILTIN_CALLS: [(&str, Construct); 7] = [
    ("getattr", Construct::Getattr),
    ("hasattr", Construct::Hasattr),
    ("setattr", Construct::Setattr),
    ("delattr", Construct::Delattr),
    ("vars", Construct::Vars),
    ("eval", Construct::Eval),
    ("exec", Construct::Exec),
];

/// A name that reaches the mapping of the builtins, or text that can write any call: a lookup by
/// string can then name each builtin function, so each of them can hide in the module.
const BUILTINS_DOORS: [&str; 5] = ["__builtins__", "builtins", "globals", "locals", "compile"];
/// An attribute that reaches the module or the mapping of the builtins from a function or a frame.
const BUILTINS_ATTRIBUTES: [&str; 6] = [
    "__builtins__",
    "f_builtins",
    "__self__",
    "__globals__",
    "f_globals",
    "f_locals",
];

fn span(node: &impl Ranged) -> (usize, usize) {
    (node.start().to_usize(), node.end().to_usize())
}

fn builtin_construct(name: &str) -> Option<Construct> {
    BUILTIN_CALLS
        .iter()
        .find_map(|(word, construct)| (*word == name).then_some(*construct))
}

/// The names that the imports of one module bind, wherever the import stands in the module.
#[derive(Default)]
struct Aliases {
    cast: HashSet<String>,
    typing: HashSet<String>,
    loaders: HashSet<String>,
    importlib: HashSet<String>,
    /// The first import of `builtins`, and the first star import from `typing` and from `importlib`.
    builtins: Option<TextRange>,
    typing_star: Option<TextRange>,
    importlib_star: Option<TextRange>,
}

impl Aliases {
    fn import(&mut self, node: &ruff_python_ast::StmtImport, at: TextRange) {
        for alias in &node.names {
            let first = alias.name.as_str().split('.').next().unwrap_or_default();
            let bound = alias.asname.as_ref().map_or(first, |name| name.as_str());
            match first {
                "typing" | "typing_extensions" => {
                    self.typing.insert(bound.to_owned());
                }
                "importlib" => {
                    self.importlib.insert(bound.to_owned());
                }
                "builtins" => {
                    self.builtins.get_or_insert(at);
                }
                _ => {}
            }
        }
    }

    fn import_from(&mut self, node: &ruff_python_ast::StmtImportFrom, at: TextRange) {
        let module = node.module.as_ref().map_or("", |name| name.as_str());
        for alias in &node.names {
            let bound = alias.asname.as_ref().unwrap_or(&alias.name).as_str();
            match (module, alias.name.as_str()) {
                ("typing" | "typing_extensions", "cast") => {
                    self.cast.insert(bound.to_owned());
                }
                ("typing" | "typing_extensions", "*") => {
                    self.typing_star.get_or_insert(at);
                }
                ("importlib", "import_module" | "__import__") => {
                    self.loaders.insert(bound.to_owned());
                }
                ("importlib", "*") => {
                    self.importlib_star.get_or_insert(at);
                }
                ("builtins", _) => {
                    self.builtins.get_or_insert(at);
                }
                _ => {}
            }
        }
    }
}

impl<'a> Visitor<'a> for Aliases {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Import(node) => self.import(node, stmt.range()),
            Stmt::ImportFrom(node) => self.import_from(node, stmt.range()),
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }
}

struct Walk<'a> {
    module: &'a Module,
    binders: &'a Binders,
    typing_unchanged: bool,
    evidence: &'a mut EvidenceMap,
    owner: String,
    records: Vec<Record<ConstructFact>>,
    signals: Vec<Record<SignalFact>>,
    support: Support,
    loaders: HashSet<String>,
    importlibs: HashSet<String>,
    casts: HashSet<String>,
    typing_modules: HashSet<String>,
    aliases: Aliases,
    /// The callee of each site that a record states: its name is no hidden use (#1537).
    consumed: HashSet<(usize, usize)>,
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
            Stmt::Expr(node) if ignores::supported_call(&node.value) => self.type_ignore(stmt),
            Stmt::Assign(_) | Stmt::Return(_) => self.type_ignore(stmt),
            Stmt::FunctionDef(node) => {
                if let Some(annotation) = &node.returns {
                    self.annotation(annotation);
                }
            }
            Stmt::AnnAssign(node) => {
                self.type_ignore(stmt);
                self.annotation(&node.annotation);
            }
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
            self.hide(Construct::BroadExcept, handler);
        }
        visitor::walk_except_handler(self, handler);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(name) => self.name(expr, name.id.as_str()),
            Expr::Attribute(node) => self.attribute(expr, node),
            Expr::Subscript(node) => self.lookup(&node.slice),
            _ => {}
        }
        if let Expr::Call(call) = expr {
            self.call(expr, call);
            self.argument_strings(call);
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

impl Walk<'_> {
    fn type_ignore(&mut self, stmt: &Stmt) {
        let start = stmt.start().to_usize();
        let end = stmt.end().to_usize();
        let location = self.module.location(stmt);
        let Ok(column) = usize::try_from(location.column) else {
            return;
        };
        let Some((tag, text)) =
            self.comments
                .take(self.module.text(), start - column, start, end, stmt)
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
        if !(self.typing_unchanged && self.binders.names_any(annotation)) {
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
        self.support.downgrade(Construct::StringLiteralCompare);
        let loader = matches!(&*call.func, Expr::Name(name)
            if name.id.as_str() == "__import__" && self.binders.builtin_visible("__import__"))
            || named_call(&call.func, &self.loaders, &self.importlibs, "import_module");
        if loader {
            self.consumed.insert(span(&*call.func));
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
            self.consumed.insert(span(&*call.func));
            self.call_signal(
                expr,
                &call.func,
                "cast_call",
                "cast",
                Signal::CastCall,
                SignalFact::CastCall,
            );
        }
        let Expr::Name(callee) = &*call.func else {
            return;
        };
        let Some(builtin) = builtin_construct(callee.id.as_str()) else {
            return;
        };
        if !self.binders.builtin_visible(callee.id.as_str()) {
            return;
        }
        self.consumed.insert(span(&*call.func));
        match builtin {
            Construct::Vars => self.construct(expr, "vars_call", "vars", ConstructFact::VarsCall),
            Construct::Getattr => self.getattr(expr),
            Construct::Setattr => {
                self.construct(expr, "setattr_call", "setattr", ConstructFact::SetattrCall);
            }
            Construct::Delattr => {
                self.construct(expr, "delattr_call", "delattr", ConstructFact::DelattrCall);
            }
            Construct::Hasattr => self.signal(
                expr,
                "hasattr_call",
                "hasattr",
                SignalFact::HasattrCall(self.signal_data(Signal::HasattrCall, None)),
            ),
            Construct::Eval => self.signal(
                expr,
                "eval_call",
                "eval",
                SignalFact::EvalCall(self.signal_data(Signal::EvalCall, None)),
            ),
            Construct::Exec => self.signal(
                expr,
                "exec_call",
                "exec",
                SignalFact::ExecCall(self.signal_data(Signal::ExecCall, None)),
            ),
            _ => {}
        }
        // A text that runs can call any builtin: no other site is proven absent from it.
        if matches!(builtin, Construct::Eval | Construct::Exec) {
            self.hide_builtins(expr);
        }
    }

    /// A name that is no callee of a recorded site. A form that binds the name again, or passes it
    /// as a value, can call it where the survey does not look (#1537).
    fn name(&mut self, expr: &Expr, id: &str) {
        if self.consumed.contains(&span(expr)) {
            return;
        }
        if let Some(construct) = builtin_construct(id) {
            self.hide(construct, expr);
        }
        if BUILTINS_DOORS.contains(&id) {
            self.hide_builtins(expr);
        }
        if id == "__dict__" {
            self.hide(Construct::DunderDict, expr);
        }
        if matches!(id, "__import__" | "import_module")
            || self.aliases.loaders.contains(id)
            || self.aliases.importlib.contains(id)
        {
            self.hide(Construct::DynamicImport, expr);
        }
        if id == "cast" || self.aliases.cast.contains(id) || self.aliases.typing.contains(id) {
            self.hide(Construct::Cast, expr);
        }
    }

    /// An attribute that is no callee of a recorded site. `x.cast`, `x.import_module` and `x.getattr`
    /// name a function of a module that the survey does not follow.
    fn attribute(&mut self, expr: &Expr, node: &ruff_python_ast::ExprAttribute) {
        if let Expr::Name(base) = &*node.value {
            let id = base.id.as_str();
            if self.aliases.typing.contains(id) || self.aliases.importlib.contains(id) {
                // The module is used by its attribute: that is no hidden use of the module name.
                self.consumed.insert(span(&*node.value));
            }
        }
        let attr = node.attr.as_str();
        if !self.consumed.contains(&span(expr)) {
            if attr == "cast" {
                self.hide(Construct::Cast, expr);
            }
            if matches!(attr, "import_module" | "__import__") {
                self.hide(Construct::DynamicImport, expr);
            }
        }
        if let Some(construct) = builtin_construct(attr) {
            self.hide(construct, expr);
        }
        if BUILTINS_ATTRIBUTES.contains(&attr) {
            self.hide_builtins(expr);
        }
    }

    /// A string that a call or a subscript reads: it names a builtin, the builtins or the dict of an
    /// object, so a lookup by that string hides a site. A name in a table, a comparison or an
    /// assignment is data until such a lookup reads it (a name that a variable holds is dynamic code).
    fn lookup(&mut self, expr: &Expr) {
        let Expr::StringLiteral(text) = expr else {
            return;
        };
        match text.value.to_str() {
            "__dict__" => self.hide(Construct::DunderDict, expr),
            "builtins" | "__builtins__" => self.hide_builtins(expr),
            other => {
                if let Some(construct) = builtin_construct(other) {
                    self.hide(construct, expr);
                }
            }
        }
    }

    /// A string that a call reads is a name that a lookup can resolve; a keyword `mode` is the mode
    /// of `ast.parse` and `compile`, no lookup.
    fn argument_strings(&mut self, call: &ruff_python_ast::ExprCall) {
        for argument in &call.arguments.args {
            self.lookup(argument);
        }
        let named = call.arguments.keywords.iter();
        let values = named.filter(|keyword| {
            keyword
                .arg
                .as_ref()
                .is_none_or(|name| name.as_str() != "mode")
        });
        for value in values.map(|keyword| &keyword.value) {
            self.lookup(value);
        }
    }

    /// The imports that hide a construct: `builtins`, and a star import from `typing` or `importlib`.
    fn hide_by_import(&mut self) {
        if let Some(at) = self.aliases.builtins {
            self.hide_builtins(&at);
        }
        if let Some(at) = self.aliases.typing_star {
            self.hide(Construct::Cast, &at);
        }
        if let Some(at) = self.aliases.importlib_star {
            self.hide(Construct::DynamicImport, &at);
        }
    }

    /// Each builtin call that the survey places can hide in this module.
    fn hide_builtins(&mut self, node: &impl Ranged) {
        for (_, construct) in BUILTIN_CALLS {
            self.hide(construct, node);
        }
    }

    /// A form that can hide a site of `construct`. The first one of each construct in a module
    /// is a record: the model reads it as a module in which the absence is not proven (#1537).
    fn hide(&mut self, construct: Construct, node: &impl Ranged) {
        if Construct::PER_MODULE.contains(&construct)
            && self.support.of(construct) == Seen::Supported
        {
            let place = self.module.location(node);
            let evidence = self.module.evidence(self.evidence, node);
            self.record(
                place,
                evidence,
                &format!("unseen_form_{}", construct.word()),
                "unseen_form",
                ConstructFact::UnseenForm(PlainConstructData {
                    construct: construct.word().to_owned(),
                    // The module, not the function: an exemption of a rule names modules.
                    owner: self.module.name.clone(),
                }),
            );
        }
        self.support.downgrade(construct);
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
