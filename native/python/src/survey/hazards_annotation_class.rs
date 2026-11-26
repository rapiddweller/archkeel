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

use std::collections::HashSet;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Comprehension, Expr, Identifier, ModModule, Operator, Pattern, Stmt};
use ruff_text_size::{Ranged, TextRange};

use crate::survey::hazards::Site;
use crate::survey::hazards_names::DYNAMIC;

/// The names that hold or run annotations.
const RESERVED: [&str; 4] = [
    "__annotations__",
    "__annotate__",
    "__annotate_func__",
    "__annotations_cache__",
];
const EVALUATORS: [&str; 5] = [
    "get_type_hints",
    "get_annotations",
    "ForwardRef",
    "_eval_type",
    "evaluate_forward_ref",
];
const BUILDERS: [&str; 3] = ["TypedDict", "NamedTuple", "make_dataclass"];
/// A call of these makes a type form, not a string.
const TYPE_FORMS: [&str; 8] = [
    "TypeVar",
    "ParamSpec",
    "TypeVarTuple",
    "NewType",
    "TypeAliasType",
    "namedtuple",
    "Enum",
    "cast",
];

/// True for `Literal` and `typing.Literal`: its strings are values, no annotation.
pub(in crate::survey::hazards) fn literal(value: &Expr) -> bool {
    named(value, "Literal")
}

fn named(value: &Expr, name: &str) -> bool {
    match value {
        Expr::Name(node) => node.id.as_str() == name,
        Expr::Attribute(node) => Identifier::as_str(&node.attr) == name,
        _ => false,
    }
}

pub(super) fn last(expr: &Expr) -> Option<&str> {
    match expr {
        Expr::Name(node) => Some(node.id.as_str()),
        Expr::Attribute(node) => Some(Identifier::as_str(&node.attr)),
        _ => None,
    }
}

struct Scan<'a> {
    evaluates: bool,
    reaches: Vec<TextRange>,
    builders: Vec<TextRange>,
    annotations: Vec<&'a Expr>,
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
        evaluates: false,
        reaches: Vec::new(),
        builders: Vec::new(),
        annotations: Vec::new(),
        tainted: HashSet::new(),
        edges: Vec::new(),
    };
    scan.visit_body(&tree.body);
    if !scan.evaluates {
        return Vec::new();
    }
    scan.close();
    let mut found = Vec::new();
    let mut add = |detail: &str, range: TextRange| {
        found.push(Site::plain(DYNAMIC, detail, range));
    };
    scan.reaches.iter().for_each(|r| add("__annotations__", *r));
    scan.builders
        .iter()
        .for_each(|r| add("annotation builder", *r));
    let mut ranges = Vec::new();
    for expr in &scan.annotations {
        scan.dynamic(expr, &mut ranges);
    }
    ranges.iter().for_each(|r| add("annotation value", *r));
    found.sort_by_key(|site| site.range.start());
    found
}

impl<'a> Scan<'a> {
    fn close(&mut self) {
        loop {
            let grown: Vec<String> = self
                .edges
                .iter()
                .filter(|(target, sources)| {
                    !self.tainted.contains(target)
                        && sources.iter().any(|s| self.tainted.contains(s))
                })
                .map(|(target, _)| target.clone())
                .collect();
            if grown.is_empty() {
                return;
            }
            self.tainted.extend(grown);
        }
    }

    fn taint(&mut self, target: &Expr) {
        match target {
            Expr::Name(node) => {
                self.tainted.insert(node.id.to_string());
            }
            Expr::Attribute(node) => {
                self.tainted.insert(node.attr.to_string());
            }
            Expr::Subscript(node) => self.taint(&node.value),
            Expr::Tuple(node) => node.elts.iter().for_each(|e| self.taint(e)),
            Expr::List(node) => node.elts.iter().for_each(|e| self.taint(e)),
            Expr::Starred(node) => self.taint(&node.value),
            _ => {}
        }
    }

    /// `target = value`. A string literal is read by the string table; a type form taints no
    /// name; a path (`Alias = other`) taints as `other` does; anything else may be a string.
    fn bind(&mut self, target: &Expr, value: &Expr) {
        if !matches!(target, Expr::Name(_) | Expr::Attribute(_)) {
            return self.taint(target);
        }
        if path(value) {
            let mut sources = Vec::new();
            ids(value, &mut sources);
            let mut names = Vec::new();
            ids(target, &mut names);
            names.truncate(1);
            self.edges
                .extend(names.into_iter().map(|n| (n, sources.clone())));
        } else if !inert(value) {
            self.taint(target);
        }
    }

    /// Push the ranges of the parts of an annotation that the survey cannot name as a type form.
    fn dynamic(&self, expr: &Expr, found: &mut Vec<TextRange>) {
        match expr {
            Expr::StringLiteral(_)
            | Expr::NoneLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::EllipsisLiteral(_) => {}
            Expr::Name(node) => {
                if self.tainted.contains(node.id.as_str()) {
                    found.push(node.range());
                }
            }
            Expr::Attribute(node) => {
                if self.tainted.contains(node.attr.as_str()) {
                    found.push(node.range());
                } else {
                    self.dynamic(&node.value, found);
                }
            }
            Expr::Subscript(node) => {
                self.dynamic(&node.value, found);
                if literal(&node.value) {
                    return;
                }
                let items = match &*node.slice {
                    Expr::Tuple(tuple) => tuple.elts.iter().collect(),
                    one => vec![one],
                };
                // The metadata of `Annotated` is no annotation.
                let count = if named(&node.value, "Annotated") {
                    1
                } else {
                    items.len()
                };
                items
                    .into_iter()
                    .take(count)
                    .for_each(|i| self.dynamic(i, found));
            }
            Expr::Tuple(node) => node.elts.iter().for_each(|e| self.dynamic(e, found)),
            Expr::List(node) => node.elts.iter().for_each(|e| self.dynamic(e, found)),
            Expr::Starred(node) => self.dynamic(&node.value, found),
            Expr::BinOp(node) if node.op == Operator::BitOr => {
                self.dynamic(&node.left, found);
                self.dynamic(&node.right, found);
            }
            other => found.push(other.range()),
        }
    }
}

/// A name, an attribute path, a subscript of one, or a union of them: a type form alias.
fn path(value: &Expr) -> bool {
    match value {
        Expr::Name(_) | Expr::NoneLiteral(_) => true,
        Expr::Attribute(node) => path(&node.value),
        Expr::Subscript(node) => path(&node.value),
        Expr::BinOp(node) => node.op == Operator::BitOr && path(&node.left) && path(&node.right),
        _ => false,
    }
}

/// The names that a path holds: each attribute name and the root name.
fn ids(value: &Expr, out: &mut Vec<String>) {
    match value {
        Expr::Name(node) => out.push(node.id.to_string()),
        Expr::Attribute(node) => {
            out.push(node.attr.to_string());
            ids(&node.value, out);
        }
        Expr::Subscript(node) => ids(&node.value, out),
        Expr::BinOp(node) => {
            ids(&node.left, out);
            ids(&node.right, out);
        }
        _ => {}
    }
}

/// A value that is no string the survey could miss: a literal, a type factory, a function.
fn inert(value: &Expr) -> bool {
    match value {
        Expr::StringLiteral(_)
        | Expr::NumberLiteral(_)
        | Expr::BooleanLiteral(_)
        | Expr::BytesLiteral(_)
        | Expr::EllipsisLiteral(_)
        | Expr::Lambda(_) => true,
        Expr::Call(call) => last(&call.func).is_some_and(|name| TYPE_FORMS.contains(&name)),
        _ => false,
    }
}

impl<'a> Visitor<'a> for Scan<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Assign(node) => node.targets.iter().for_each(|t| self.bind(t, &node.value)),
            Stmt::AnnAssign(node) => {
                if let Some(value) = &node.value {
                    self.bind(&node.target, value);
                }
            }
            Stmt::AugAssign(node) => self.taint(&node.target),
            Stmt::For(node) => self.taint(&node.target),
            Stmt::With(node) => node
                .items
                .iter()
                .filter_map(|item| item.optional_vars.as_deref())
                .for_each(|target| self.taint(target)),
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_annotation(&mut self, expr: &'a Expr) {
        self.annotations.push(expr);
        visitor::walk_expr(self, expr);
    }

    fn visit_comprehension(&mut self, comprehension: &'a Comprehension) {
        self.taint(&comprehension.target);
        visitor::walk_comprehension(self, comprehension);
    }

    fn visit_pattern(&mut self, pattern: &'a Pattern) {
        let name = match pattern {
            Pattern::MatchAs(node) => node.name.as_ref(),
            Pattern::MatchStar(node) => node.name.as_ref(),
            Pattern::MatchMapping(node) => node.rest.as_ref(),
            _ => None,
        };
        if let Some(name) = name {
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
            self.evaluates = true;
        }
        match expr {
            Expr::StringLiteral(text) if text.value.to_str() == "__annotations__" => {
                self.reaches.push(expr.range());
            }
            Expr::Call(call) => {
                let callee = last(&call.func);
                let eval_str = call
                    .arguments
                    .keywords
                    .iter()
                    .any(|k| k.arg.as_ref().is_some_and(|a| a.as_str() == "eval_str"));
                self.evaluates |= eval_str;
                let literal_ref =
                    matches!(call.arguments.args.first(), Some(Expr::StringLiteral(_)));
                let build = callee.is_some_and(|n| BUILDERS.contains(&n))
                    || (callee == Some("ForwardRef") && !literal_ref);
                if build {
                    self.builders.push(expr.range());
                }
            }
            Expr::Named(node) => self.taint(&node.target),
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}
