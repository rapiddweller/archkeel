// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The class rule of AD-1173 (#2093). A module that evaluates annotations (`get_type_hints`,
//! `get_annotations`, `ForwardRef`, `signature(eval_str=True)`) runs each string that reaches an
//! annotation. The survey cannot follow every way that a string gets there, so in such a module:
//! - any reach of `__annotations__` as a value is a site;
//! - a call that builds annotations from data (`TypedDict(..)`, `NamedTuple(..)`,
//!   `ForwardRef(name)`) is a site;
//! - an annotation that holds a value the survey cannot name as a type form is a site: a call, a
//!   condition, a computed string, a name that the module binds to anything but a string literal
//!   or a type form.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Comprehension, Expr, ExprCall, ExprStringLiteral, ModModule, Operator, Pattern, PatternMatchAs,
    PatternMatchMapping, PatternMatchStar, Stmt,
};
use ruff_text_size::{Ranged, TextRange};

use super::super::trojan_horse::Site;
use super::forms::{assigned, ids, inert, items, last, literal, path, TYPE_FORMS};
use super::imports::{Imports, EVALUATORS};
use crate::parse::Unread;
use crate::survey::hazards_names::DYNAMIC;

/// The names that hold or run annotations.
const RESERVED: [&str; 4] = [
    "__annotations__",
    "__annotate__",
    "__annotate_func__",
    "__annotations_cache__",
];
/// The texts that one name may hold before the name is a site.
const MAX_TEXTS: usize = 8;
const BUILDERS: [&str; 3] = ["TypedDict", "NamedTuple", "make_dataclass"];
struct Scan<'a> {
    imports: Imports,
    reaches: Vec<TextRange>,
    /// `(callee, first argument is a string literal, range)` of each call.
    calls: Vec<(String, bool, TextRange)>,
    /// The names and attribute names that the module binds to a string literal.
    texts: HashMap<String, Vec<&'a ExprStringLiteral>>,
    /// Each `target = value`, read when the walk is over: the imports are known then.
    binds: Vec<(&'a Expr, &'a Expr)>,
    /// The names that the module defines or assigns: they may shadow a type factory.
    defs: HashSet<String>,
    annotations: Vec<&'a Expr>,
    /// In a function body: Python neither evaluates nor stores a local variable annotation.
    local: bool,
    /// The names and attribute names that the module binds to a value that may be a string.
    tainted: HashSet<String>,
    /// `target = source`: the target is as tainted as its sources.
    edges: Vec<(String, Vec<String>)>,
}

/// `found` and the sites of the class rule.
pub(in crate::survey::hazards) fn with(mut found: Vec<Site>, tree: &ModModule) -> Vec<Site> {
    found.extend(sites(tree));
    found
}

/// The sites of the class rule for one module, none when it evaluates no annotation.
fn sites(tree: &ModModule) -> Vec<Site> {
    let mut scan = Scan {
        imports: Imports::new(),
        reaches: Vec::new(),
        calls: Vec::new(),
        texts: HashMap::new(),
        binds: Vec::new(),
        defs: HashSet::new(),
        annotations: Vec::new(),
        local: false,
        tainted: HashSet::new(),
        edges: Vec::new(),
    };
    scan.visit_body(&tree.body);
    if !scan.imports.evaluates {
        return Vec::new();
    }
    scan.settle();
    scan.close();
    let mut found = Vec::new();
    let mut add = |detail: &str, range: TextRange| {
        found.push(Site::plain(DYNAMIC, detail, range));
    };
    scan.reaches.iter().for_each(|r| add("__annotations__", *r));
    for (callee, literal_ref, range) in &scan.calls {
        let name = scan.imports.real(callee);
        // The walker of AD-1095 reads a literal argument only under the spelling `ForwardRef`.
        let read = *literal_ref && callee == "ForwardRef";
        if BUILDERS.contains(&name) || (name == "ForwardRef" && !read) {
            add("annotation builder", *range);
        }
    }
    let mut ranges = Vec::new();
    for expr in &scan.annotations {
        scan.dynamic(expr, &mut ranges, 0);
    }
    ranges.iter().for_each(|r| add("annotation value", *r));
    found.sort_by_key(|site| site.range.start());
    found
}

impl<'a> Scan<'a> {
    /// Taint flows from a source to each target that is an alias of it; one pass over the edges.
    fn close(&mut self) {
        let mut targets: HashMap<&str, Vec<&str>> = HashMap::new();
        for (target, sources) in &self.edges {
            for source in sources {
                targets.entry(source).or_default().push(target);
            }
        }
        // An alias of a held string is as uncertain as an alias of a tainted name.
        let seeds = self.tainted.iter().chain(self.texts.keys());
        let mut queue: Vec<&str> = seeds.map(String::as_str).collect();
        let mut seen: HashSet<&str> = queue.iter().copied().collect();
        let mut grown: Vec<String> = Vec::new();
        while let Some(source) = queue.pop() {
            let next = targets.get(source).into_iter().flatten();
            for target in next.filter(|target| seen.insert(**target)) {
                queue.push(target);
                grown.push((*target).to_owned());
            }
        }
        self.tainted.extend(grown);
    }

    fn settle(&mut self) {
        for (target, value) in std::mem::take(&mut self.binds) {
            if let Expr::Name(name) = target {
                self.defs.insert(name.id.to_string());
            }
            self.bind(target, value);
        }
    }

    /// A call that makes a type form: the callee is a factory of `typing`, `enum` or
    /// `collections` that the module does not define or assign.
    fn factory(&self, call: &ExprCall) -> bool {
        let real = self.imports.standard(&call.func);
        real.is_some_and(|name| TYPE_FORMS.contains(&name))
            && !last(&call.func).is_some_and(|n| self.defs.contains(n))
    }

    fn taint(&mut self, target: &Expr) {
        match target {
            Expr::Subscript(node) => self.taint(&node.value),
            Expr::Tuple(node) => node.elts.iter().for_each(|e| self.taint(e)),
            Expr::List(node) => node.elts.iter().for_each(|e| self.taint(e)),
            Expr::Starred(node) => self.taint(&node.value),
            other => {
                if let Some(id) = last(other) {
                    self.tainted.insert(id.to_owned());
                }
            }
        }
    }

    /// `target = value`. A string literal is read by the string table; a type form taints no
    /// name; a path (`Alias = other`) taints as `other` does; anything else may be a string.
    fn bind(&mut self, target: &'a Expr, value: &'a Expr) {
        if !matches!(target, Expr::Name(_) | Expr::Attribute(_)) {
            return self.taint(target);
        }
        if let (true, Some(id), Some(source)) = (path(value), last(target), last(value)) {
            // `TD = typing.TypedDict`: the alias builds annotations as the original does.
            let real = self.imports.real(source);
            if BUILDERS.contains(&real) || real == "ForwardRef" {
                let real = real.to_owned();
                self.imports.aliases.insert(id.to_owned(), real);
            }
        }
        if let (Expr::StringLiteral(text), Some(id)) = (value, last(target)) {
            let texts = self.texts.entry(id.to_owned()).or_default();
            texts.push(text);
            // A name with many texts costs a parse for each text at each annotation.
            if texts.len() > MAX_TEXTS {
                self.taint(target);
            }
        }
        if path(value) {
            let mut sources = Vec::new();
            ids(value, &mut sources);
            let mut names = Vec::new();
            ids(target, &mut names);
            names.truncate(1);
            self.edges
                .extend(names.into_iter().map(|n| (n, sources.clone())));
        } else if !inert(value, &|call| self.factory(call)) {
            self.taint(target);
        }
    }

    /// A name in an annotation: a tainted name is a site; the texts of a held name get the same
    /// checks as a quoted annotation, one level deep (a held name inside them is a site).
    fn name(&self, id: &str, expr: &Expr, found: &mut Vec<TextRange>, depth: usize) {
        if self.tainted.contains(id) || (depth > 0 && self.texts.contains_key(id)) {
            found.push(expr.range());
            return;
        }
        for text in self.texts.get(id).into_iter().flatten() {
            self.quoted(text, found, depth);
        }
    }

    /// A quoted annotation is read as code: the same checks apply to its text.
    fn quoted(&self, text: &ExprStringLiteral, found: &mut Vec<TextRange>, depth: usize) {
        let mut inner = Vec::new();
        match crate::parse::expression(text.value.to_str()) {
            Ok(code) if depth < 8 => self.dynamic(&code, &mut inner, depth + 1),
            Ok(_) | Err(Unread::Bound) => inner.push(text.range()),
            Err(Unread::Syntax) => {}
        }
        if !inner.is_empty() {
            found.push(text.range());
        }
    }

    /// Push the ranges of the parts of an annotation that the survey cannot name as a type form.
    fn dynamic(&self, expr: &Expr, found: &mut Vec<TextRange>, depth: usize) {
        match expr {
            Expr::StringLiteral(text) => self.quoted(text, found, depth),
            Expr::NoneLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::EllipsisLiteral(_) => {}
            Expr::Name(node) => self.name(node.id.as_str(), expr, found, depth),
            Expr::Attribute(node) => {
                let attr = node.attr.as_str();
                if self.tainted.contains(attr) || self.texts.contains_key(attr) {
                    self.name(attr, expr, found, depth);
                } else {
                    self.dynamic(&node.value, found, depth);
                }
            }
            Expr::Subscript(node) => {
                self.dynamic(&node.value, found, depth);
                if literal(&node.value) {
                    return;
                }
                items(node)
                    .into_iter()
                    .for_each(|i| self.dynamic(i, found, depth));
            }
            Expr::Tuple(node) => node.elts.iter().for_each(|e| self.dynamic(e, found, depth)),
            Expr::List(node) => node.elts.iter().for_each(|e| self.dynamic(e, found, depth)),
            Expr::Starred(node) => self.dynamic(&node.value, found, depth),
            Expr::BinOp(node) if node.op == Operator::BitOr => {
                self.dynamic(&node.left, found, depth);
                self.dynamic(&node.right, found, depth);
            }
            other => found.push(other.range()),
        }
    }
}

impl<'a> Visitor<'a> for Scan<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        assigned(stmt, |target, value| self.binds.push((target, value)));
        match stmt {
            Stmt::FunctionDef(node) => self.defs.insert(node.name.to_string()),
            Stmt::ClassDef(node) => self.defs.insert(node.name.to_string()),
            _ => false,
        };
        match stmt {
            Stmt::AugAssign(node) => self.taint(&node.target),
            Stmt::For(node) => self.taint(&node.target),
            Stmt::With(node) => node
                .items
                .iter()
                .filter_map(|item| item.optional_vars.as_deref())
                .for_each(|target| self.taint(target)),
            // An evaluator that the module imports under another name is an evaluator.
            Stmt::Import(node) => self.imports.add(None, &node.names),
            Stmt::ImportFrom(node) => {
                let module = node.module.as_deref().filter(|_| node.level == 0);
                self.imports.add(module, &node.names);
            }
            Stmt::FunctionDef(node) => {
                node.decorator_list
                    .iter()
                    .for_each(|d| self.visit_decorator(d));
                node.type_params
                    .iter()
                    .for_each(|p| self.visit_type_params(p));
                // The signature of a function is evaluated in the scope that holds the function.
                let outer = std::mem::replace(&mut self.local, false);
                self.visit_parameters(&node.parameters);
                node.returns.iter().for_each(|r| self.visit_annotation(r));
                self.local = true;
                self.visit_body(&node.body);
                self.local = outer;
                return;
            }
            Stmt::ClassDef(_) => {
                // A class body runs, so its annotations are evaluated, also inside a function.
                let outer = std::mem::replace(&mut self.local, false);
                visitor::walk_stmt(self, stmt);
                self.local = outer;
                return;
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_annotation(&mut self, expr: &'a Expr) {
        if !self.local {
            self.annotations.push(expr);
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_comprehension(&mut self, comprehension: &'a Comprehension) {
        self.taint(&comprehension.target);
        visitor::walk_comprehension(self, comprehension);
    }

    fn visit_pattern(&mut self, pattern: &'a Pattern) {
        if let Pattern::MatchAs(PatternMatchAs {
            name: Some(name), ..
        })
        | Pattern::MatchStar(PatternMatchStar {
            name: Some(name), ..
        })
        | Pattern::MatchMapping(PatternMatchMapping {
            rest: Some(name), ..
        }) = pattern
        {
            self.tainted.insert(name.to_string());
        }
        visitor::walk_pattern(self, pattern);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        let name = last(expr);
        if name.is_some_and(|n| RESERVED.contains(&n)) {
            self.reaches.push(expr.range());
        }
        if name.is_some_and(|n| EVALUATORS.contains(&n)) {
            self.imports.evaluates = true;
        }
        match expr {
            Expr::StringLiteral(text) => {
                let text = text.value.to_str();
                if RESERVED.contains(&text) {
                    self.reaches.push(expr.range());
                }
                // An evaluator that the module looks up by name is an evaluator.
                self.imports.evaluates |= EVALUATORS.contains(&text);
            }
            Expr::Call(call) => {
                let callee = last(&call.func);
                let eval_str = call
                    .arguments
                    .keywords
                    .iter()
                    .any(|k| k.arg.as_ref().is_some_and(|a| a.as_str() == "eval_str"));
                self.imports.evaluates |= eval_str;
                let literal_ref =
                    matches!(call.arguments.args.first(), Some(Expr::StringLiteral(_)));
                if let Some(callee) = callee {
                    self.calls
                        .push((callee.to_owned(), literal_ref, expr.range()));
                }
            }
            Expr::Named(node) => self.taint(&node.target),
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}
