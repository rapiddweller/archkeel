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

use std::cell::{Cell, OnceCell};
use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Expr, ExprCall, ExprStringLiteral, Operator};
use ruff_text_size::{Ranged, TextRange};

use super::super::trojan_horse::Site;
use super::forms::{items, last, literal, TYPE_FORMS};
use super::scopes::{build, Binding, Facts, Kind, ScopeId};
use crate::module::Module;
use crate::parse::Unread;
use crate::survey::hazards_names::DYNAMIC;

/// Modules whose names are type forms, never strings (the owner's fixed list).
const STANDARD: [&str; 12] = [
    "typing",
    "typing_extensions",
    "collections.abc",
    "builtins",
    "enum",
    "dataclasses",
    "abc",
    "types",
    "datetime",
    "decimal",
    "uuid",
    "pathlib",
];
const BUILDERS: [&str; 3] = ["TypedDict", "NamedTuple", "make_dataclass"];
/// A name with more bindings than this is a site: each binding costs a read.
const MAX_BINDINGS: usize = 8;
/// A string inside a string is read to this depth; so is a chain of names.
const MAX_DEPTH: usize = 8;
/// The reads of one module; over it the rest of the module is a site.
const BUDGET: usize = 200_000;

/// What a name or path stands for.
#[derive(Clone, PartialEq)]
enum Entity {
    /// A type form that is no receiver: a class instance, an alias, a factory result.
    Clean,
    /// A name of a standard typing-style module (or a builtin).
    Standard(String),
    Module(String),
    Class(usize, ScopeId),
    Unknown,
}

pub(in crate::survey) struct Project<'a> {
    modules: &'a [Module],
    by_name: HashMap<&'a str, usize>,
    facts: Vec<OnceCell<Facts<'a>>>,
    budget: Cell<usize>,
}

/// The names that a read is in the middle of: a cycle is not clean.
type Active = Vec<(usize, ScopeId, String)>;

impl<'a> Project<'a> {
    pub(in crate::survey) fn of(modules: &'a [Module]) -> Self {
        Self {
            modules,
            by_name: modules
                .iter()
                .enumerate()
                .map(|(at, m)| (m.name.as_str(), at))
                .collect(),
            facts: modules.iter().map(|_| OnceCell::new()).collect(),
            budget: Cell::new(0),
        }
    }

    fn facts(&self, at: usize) -> &Facts<'a> {
        self.facts[at].get_or_init(|| build(&self.modules[at]))
    }

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
                Entity::Standard(name) => name,
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
    fn dynamic(
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

    fn each(
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

    fn clean(&self, expr: &Expr, at: (usize, ScopeId), depth: usize, active: &mut Active) -> bool {
        let mut found = Vec::new();
        self.dynamic(expr, at, &mut found, depth, active);
        found.is_empty()
    }

    /// A quoted annotation is read as code: the same rule applies to its text. A text that does
    /// not parse raises `SyntaxError` and imports nothing; a text over the parser bound is not clean.
    fn text(
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

    /// What `expr` evaluates to, as far as an annotation can use it.
    fn path(
        &self,
        expr: &Expr,
        m: usize,
        scope: ScopeId,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        if depth > MAX_DEPTH * 2 || self.budget.get() == 0 {
            return Entity::Unknown;
        }
        self.budget.set(self.budget.get() - 1);
        match expr {
            Expr::Name(node) => self.name(node.id.as_str(), m, scope, depth, active),
            Expr::Attribute(node) => {
                let base = self.path(&node.value, m, scope, depth + 1, active);
                self.step(base, node.attr.as_str(), depth, active)
            }
            _ => Entity::Unknown,
        }
    }

    fn name(
        &self,
        id: &str,
        m: usize,
        scope: ScopeId,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        let facts = self.facts(m);
        if facts.opaque {
            return Entity::Unknown;
        }
        let key = (m, scope, id.to_owned());
        if active.contains(&key) {
            return Entity::Unknown;
        }
        if let Some(at) = self.holder(facts, scope, id) {
            active.push(key);
            let entity = self.merge(m, at, &facts.scopes[at].names[id], depth, active);
            active.pop();
            return entity;
        }
        let stars = &facts.scopes[0].stars;
        self.merge_all(
            stars
                .iter()
                .map(|star| self.member(star, id, depth, active)),
        )
    }

    /// The scope that binds `id` for code in `scope`: a class scope is read only by its own body.
    fn holder(&self, facts: &Facts<'a>, scope: ScopeId, id: &str) -> Option<ScopeId> {
        let chain = std::iter::successors(Some(scope), |at| facts.scopes[*at].parent);
        let mut visible = chain.filter(|at| facts.scopes[*at].kind != Kind::Class || *at == scope);
        visible.find(|at| facts.scopes[*at].names.contains_key(id))
    }

    fn merge(
        &self,
        m: usize,
        scope: ScopeId,
        bindings: &[Binding<'a>],
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        // An equal text adds no value: a name with many equal texts is as clean as with one.
        let mut texts = HashSet::new();
        let distinct: Vec<&Binding<'a>> = bindings
            .iter()
            .filter(|b| match b {
                Binding::Value(Expr::StringLiteral(text)) => texts.insert(text.value.to_str()),
                _ => true,
            })
            .collect();
        if distinct.len() > MAX_BINDINGS {
            return Entity::Unknown;
        }
        let found = distinct
            .into_iter()
            .map(|b| self.binding(m, scope, b, depth, active));
        self.merge_all(found.collect::<Vec<_>>().into_iter())
    }

    /// All entities agree: that one; all are clean but differ: a type form that is no receiver.
    fn merge_all(&self, entities: impl Iterator<Item = Entity>) -> Entity {
        let all: Vec<Entity> = entities.collect();
        match all.first() {
            None => Entity::Standard(String::new()),
            Some(_) if all.contains(&Entity::Unknown) => Entity::Unknown,
            Some(first) if all.iter().all(|e| e == first) => first.clone(),
            Some(_) => Entity::Clean,
        }
    }

    fn binding(
        &self,
        m: usize,
        scope: ScopeId,
        binding: &Binding<'a>,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        match binding {
            Binding::Value(value) => self.value(value, m, scope, depth + 1, active),
            Binding::Class(body) => Entity::Class(m, *body),
            Binding::Inert => Entity::Clean,
            Binding::Import(module, None) => self.module(module),
            Binding::Import(module, Some(name)) => self.member(module, name, depth, active),
            Binding::Unknown => Entity::Unknown,
        }
    }

    fn value(
        &self,
        value: &Expr,
        m: usize,
        scope: ScopeId,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        let clean = |ok: bool| if ok { Entity::Clean } else { Entity::Unknown };
        match value {
            Expr::Name(_) | Expr::Attribute(_) => self.path(value, m, scope, depth, active),
            Expr::StringLiteral(text) => clean(self.text(text, (m, scope), depth, active)),
            Expr::NoneLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::EllipsisLiteral(_)
            | Expr::Lambda(_) => Entity::Clean,
            Expr::Call(call) => clean(self.factory(call, m, scope, depth, active)),
            Expr::Subscript(_) | Expr::BinOp(_) | Expr::Tuple(_) | Expr::List(_) => {
                clean(self.clean(value, (m, scope), depth, active))
            }
            _ => Entity::Unknown,
        }
    }

    /// A call of a standard type factory whose arguments after the name are clean: `bound=`,
    /// the constraints and `default=` are annotations, and Python evaluates their strings.
    fn factory(
        &self,
        call: &ExprCall,
        m: usize,
        scope: ScopeId,
        depth: usize,
        active: &mut Active,
    ) -> bool {
        let Entity::Standard(name) = self.path(&call.func, m, scope, depth, active) else {
            return false;
        };
        let rest = call.arguments.args.iter().skip(1);
        let keywords = call.arguments.keywords.iter().map(|k| &k.value);
        TYPE_FORMS.contains(&name.as_str())
            && rest
                .chain(keywords)
                .all(|arg| self.clean(arg, (m, scope), depth, active))
    }

    /// `import m`: a module that the scan holds, or a standard one, or a prefix of one.
    fn module(&self, name: &str) -> Entity {
        let prefix = format!("{name}.");
        let partial = STANDARD.iter().any(|s| s.starts_with(&prefix));
        if STANDARD.contains(&name) || self.by_name.contains_key(name) || partial {
            return Entity::Module(name.to_owned());
        }
        Entity::Unknown
    }

    /// The name `name` of module `module`: standard (clean), a scanned module (its own binding),
    /// a submodule, or else unknown (a third-party or other standard module: no record proves it).
    fn member(&self, module: &str, name: &str, depth: usize, active: &mut Active) -> Entity {
        let full = format!("{module}.{name}");
        if let sub @ Entity::Module(_) = self.module(&full) {
            return sub;
        }
        if STANDARD.contains(&module) {
            return Entity::Standard(name.to_owned());
        }
        let Some(&at) = self.by_name.get(module) else {
            return Entity::Unknown;
        };
        let facts = self.facts(at);
        let top = &facts.scopes[0];
        if !top.names.contains_key(name)
            && top.stars.is_empty()
            && !top.names.contains_key("__getattr__")
        {
            return Entity::Standard(name.to_owned());
        }
        if top.names.contains_key("__getattr__") && !top.names.contains_key(name) {
            return Entity::Unknown;
        }
        self.name(name, at, 0, depth + 1, active)
    }

    /// Step from an entity to its attribute.
    fn step(&self, base: Entity, attr: &str, depth: usize, active: &mut Active) -> Entity {
        match base {
            Entity::Standard(_) => Entity::Standard(attr.to_owned()),
            Entity::Module(module) => self.member(&module, attr, depth, active),
            Entity::Class(m, body) => self.attribute(m, body, attr, depth, active),
            Entity::Clean | Entity::Unknown => Entity::Unknown,
        }
    }

    /// The attribute of a class of the scan: its own bindings and every store of that name
    /// (for any receiver), else the attribute of its bases.
    fn attribute(
        &self,
        m: usize,
        body: ScopeId,
        attr: &str,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        let facts = self.facts(m);
        if facts.opaque || depth > MAX_DEPTH * 2 {
            return Entity::Unknown;
        }
        let scope = &facts.scopes[body];
        let own = scope.names.get(attr).into_iter().flatten();
        let stored = facts.stores.get(attr).into_iter().flatten();
        let bound: Vec<&Binding<'a>> = own.chain(stored).collect();
        if !bound.is_empty() {
            let found = bound
                .into_iter()
                .map(|b| self.binding(m, body, b, depth, active));
            return self.merge_all(found.collect::<Vec<_>>().into_iter());
        }
        let Some(class) = scope.class else {
            return Entity::Unknown;
        };
        let metaclass = class
            .arguments
            .iter()
            .flat_map(|a| &a.keywords)
            .any(|k| k.arg.as_ref().is_some_and(|n| n.as_str() == "metaclass"));
        if metaclass {
            return Entity::Unknown;
        }
        let parent = scope.parent.unwrap_or(0);
        let bases = class.arguments.iter().flat_map(|a| &a.args);
        let found: Vec<Entity> = bases
            .map(|base| match self.path(base, m, parent, depth + 1, active) {
                Entity::Standard(_) => Entity::Standard(attr.to_owned()),
                Entity::Class(m2, b2) => self.attribute(m2, b2, attr, depth + 1, active),
                _ => Entity::Unknown,
            })
            .collect();
        self.merge_all(found.into_iter())
    }
}
