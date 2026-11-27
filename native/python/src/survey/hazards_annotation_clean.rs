// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed-binding rule of AD-1175 (#2156). A module that evaluates annotations runs each string
//! that reaches an annotation. An annotation-valued expression is *clean* when every binding that
//! can give its value is a type form the survey reads: a builtin, a class or function, an import of
//! a standard typing-style module or of a clean name of a scanned module, an assignment of a clean
//! value. Anything else, and each name that the module binds by a write the table cannot read, is a
//! `dynamic_import` site. The same holds for any reach of `__annotations__` and for a call that
//! builds annotations from data (`TypedDict(..)`, `NamedTuple(..)`, `ForwardRef(name)`).

use ruff_python_ast::{Expr, ExprCall, ExprStringLiteral, Operator};
use ruff_text_size::{Ranged, TextRange};

use super::super::trojan_horse::Site;
use super::entity::{Active, Entity, Project, BUDGET, BUILDERS, MAX_DEPTH};
use super::facts::ScopeId;
use super::forms::{items, last, literal, TYPE_FORMS};
use crate::parse::Unread;
use crate::survey::hazards_names::DYNAMIC;

impl<'a> Project<'a> {
    /// The sites of the rule for one module; none when it evaluates no annotation.
    pub(in crate::survey) fn sites(&self, at: usize) -> Vec<Site> {
        let facts = self.facts(at);
        if !facts.evaluates {
            return Vec::new();
        }
        self.budget.set(BUDGET);
        let mut found = Vec::new();
        let mut add = |detail: &str, range: TextRange| {
            found.push(Site::plain(DYNAMIC, detail, range));
        };
        facts
            .reaches
            .iter()
            .for_each(|r| add("__annotations__", *r));
        for call in &facts.calls {
            let real = match self.path(call.callee, at, call.scope, 0, &mut Vec::new()) {
                Entity::Standard(path) => path.rsplit('.').next().unwrap_or_default().to_owned(),
                _ => String::new(),
            };
            let spelled = last(call.callee).unwrap_or_default();
            let named = |name: &str| real == name || spelled == name;
            let read = call.literal_ref && spelled == "ForwardRef";
            if BUILDERS.iter().any(|b| named(b)) || (named("ForwardRef") && !read) {
                add("annotation builder", call.range);
            }
        }
        let mut ranges = Vec::new();
        for (expr, scope) in &facts.annotations {
            self.dynamic(expr, (at, *scope), &mut ranges, 0, &mut Vec::new());
        }
        ranges.iter().for_each(|r| add("annotation value", *r));
        found.sort_by_key(|site| site.range.start());
        found
    }

    /// Push the ranges of the parts of an annotation that are not clean.
    pub(super) fn dynamic(
        &self,
        expr: &Expr,
        at: (usize, ScopeId),
        found: &mut Vec<TextRange>,
        depth: usize,
        active: &mut Active,
    ) {
        match expr {
            Expr::StringLiteral(text) => {
                if !self.text(text, at, depth, active) {
                    found.push(text.range());
                }
            }
            Expr::NoneLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::EllipsisLiteral(_) => {}
            Expr::Name(_) | Expr::Attribute(_) => {
                if self.path(expr, at.0, at.1, depth, active) == Entity::Unknown {
                    found.push(expr.range());
                }
            }
            Expr::Subscript(node) => {
                self.dynamic(&node.value, at, found, depth, active);
                let parts = if literal(&node.value) {
                    Vec::new()
                } else {
                    items(node)
                };
                for part in parts {
                    self.dynamic(part, at, found, depth, active);
                }
            }
            Expr::Tuple(node) => self.each(&node.elts, at, found, depth, active),
            Expr::List(node) => self.each(&node.elts, at, found, depth, active),
            Expr::Starred(node) => self.dynamic(&node.value, at, found, depth, active),
            Expr::BinOp(node) if node.op == Operator::BitOr => {
                self.dynamic(&node.left, at, found, depth, active);
                self.dynamic(&node.right, at, found, depth, active);
            }
            other => found.push(other.range()),
        }
    }

    pub(super) fn each(
        &self,
        parts: &[Expr],
        at: (usize, ScopeId),
        found: &mut Vec<TextRange>,
        depth: usize,
        active: &mut Active,
    ) {
        for part in parts {
            self.dynamic(part, at, found, depth, active);
        }
    }

    pub(super) fn clean(
        &self,
        expr: &Expr,
        at: (usize, ScopeId),
        depth: usize,
        active: &mut Active,
    ) -> bool {
        let mut found = Vec::new();
        self.dynamic(expr, at, &mut found, depth, active);
        found.is_empty()
    }

    /// A quoted annotation is read as code: the same rule applies to its text. A text that does
    /// not parse raises `SyntaxError` and imports nothing; a text over the parser bound is not clean.
    pub(super) fn text(
        &self,
        text: &ExprStringLiteral,
        at: (usize, ScopeId),
        depth: usize,
        active: &mut Active,
    ) -> bool {
        match crate::parse::expression(text.value.to_str()) {
            Ok(code) if depth < MAX_DEPTH => self.clean(&code, at, depth + 1, active),
            Ok(_) | Err(Unread::Bound) => false,
            Err(Unread::Syntax) => true,
        }
    }

    /// A call of a standard type factory whose arguments after the name are clean: `bound=`,
    /// the constraints and `default=` are annotations, and Python evaluates their strings.
    pub(super) fn factory(
        &self,
        call: &ExprCall,
        m: usize,
        scope: ScopeId,
        depth: usize,
        active: &mut Active,
    ) -> bool {
        let Entity::Standard(path) = self.path(&call.func, m, scope, depth, active) else {
            return false;
        };
        let name = path.rsplit('.').next().unwrap_or_default().to_owned();
        let rest = call.arguments.args.iter().skip(1);
        let keywords = call.arguments.keywords.iter().map(|k| &k.value);
        TYPE_FORMS.contains(&name.as_str())
            && rest
                .chain(keywords)
                .all(|arg| self.clean(arg, (m, scope), depth, active))
    }
}
