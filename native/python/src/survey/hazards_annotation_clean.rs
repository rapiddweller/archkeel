// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The closed-binding rule of AD-1175 (#2156). In a module that evaluates annotations, an
//! annotation-valued expression is *clean* when every binding that can give its value is a type form
//! the survey reads (AD-1175 lists them). Anything else, a reach of `__annotations__` and a call that
//! builds annotations from data is a `dynamic_import` site.

use std::collections::HashSet;

use ruff_python_ast::{
    Decorator, Expr, ExprCall, ExprList, ExprStringLiteral, ExprTuple, Keyword, Operator,
};
use ruff_text_size::{Ranged, TextRange};

use super::entity::{typing_style, Active, Entity, Project, MAX_BINDINGS, MAX_DEPTH};
use super::facts::{Binding, Kind, ScopeId, TEXT};
use super::forms::{items, keeps, literal, type_subscription, TYPE_FORMS};
use crate::parse::Unread;

impl<'a> Project<'a> {
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
                if !self.text(text, depth, active) {
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
                // `os.environ['X']` is data: only a type form subscripts to a type.
                let base = self.path(&node.value, at.0, at.1, depth, active);
                if matches!(base, Entity::Standard(path) if !type_subscription(&path)) {
                    found.push(node.range());
                }
                let parts = if literal(&node.value) {
                    Vec::new()
                } else {
                    items(node)
                };
                for part in parts {
                    self.dynamic(part, at, found, depth, active);
                }
            }
            Expr::Tuple(ExprTuple { elts, .. }) | Expr::List(ExprList { elts, .. }) => {
                for elt in elts {
                    self.dynamic(elt, at, found, depth, active);
                }
            }
            Expr::Starred(node) => self.dynamic(&node.value, at, found, depth, active),
            Expr::BinOp(node) if node.op == Operator::BitOr => {
                self.dynamic(&node.left, at, found, depth, active);
                self.dynamic(&node.right, at, found, depth, active);
            }
            other => found.push(other.range()),
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

    /// A quoted annotation is read as code. A text that does not parse imports nothing.
    pub(super) fn text(&self, text: &ExprStringLiteral, depth: usize, active: &mut Active) -> bool {
        // The text is read where the annotated object is evaluated, not where the string is held.
        let at = self.context.get();
        match crate::parse::expression(text.value.to_str()) {
            Ok(code) if depth < MAX_DEPTH => {
                self.clean(&code, (at.0, at.1 | TEXT), depth + 1, active)
            }
            Ok(_) | Err(Unread::Bound) => false,
            Err(Unread::Syntax) => true,
        }
    }

    /// What a definition stands for once its decorators ran: a decorator that keeps what it gets (`dataclass`, `total_ordering`, ..) returns the class; any other can return any value.
    fn decorated(
        &self,
        decorators: &[Decorator],
        at: (usize, ScopeId),
        plain: Entity,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        let keeps_it = |d: &Decorator| {
            let callee = match &d.expression {
                Expr::Call(call) => &*call.func,
                other => other,
            };
            let entity = self.path(callee, at.0, at.1, depth, active);
            matches!(entity, Entity::Standard(path) if keeps(&path))
        };
        if decorators.iter().all(keeps_it) {
            plain
        } else {
            Entity::Unknown
        }
    }

    /// A standard type factory call whose arguments after the name (`bound=`, ..) are clean.
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

    /// What `expr` evaluates to, as far as an annotation can use it.
    pub(super) fn path(
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

    pub(super) fn name(
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
        let holders = facts.holders(scope, id);
        // A write into the module through an alias of it (`me.s = v`) changes the bare name too.
        let class = facts.scopes[scope & !TEXT].kind == Kind::Class;
        let at_module = holders.is_empty() || holders.contains(&0) || class || scope & TEXT != 0;
        if at_module && self.written(&self.modules[m].name, id) {
            return Entity::Unknown;
        }
        if !holders.is_empty() {
            let bindings = holders.iter().flat_map(|at| &facts.scopes[*at].names[id]);
            active.push(key);
            let entity = self.merge(m, bindings.collect(), depth, active);
            active.pop();
            return entity;
        }
        let stars = &facts.scopes[0].stars;
        if stars.is_empty() {
            return Entity::Standard(id.to_owned());
        }
        let found = stars
            .iter()
            .map(|star| self.member(star, id, depth, active));
        self.merge_all(found.collect::<Vec<_>>().into_iter())
    }

    pub(super) fn merge(
        &self,
        m: usize,
        bindings: Vec<&Binding<'a>>,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        // An equal text adds no value: a name with many equal texts is as clean as with one.
        let mut texts = HashSet::new();
        let distinct: Vec<&Binding<'a>> = bindings
            .into_iter()
            .filter(|b| match b {
                Binding::Value(Expr::StringLiteral(text), _) => texts.insert(text.value.to_str()),
                _ => true,
            })
            .collect();
        if distinct.len() > MAX_BINDINGS {
            return Entity::Unknown;
        }
        let found = distinct
            .into_iter()
            .map(|b| self.binding(m, b, depth, active));
        self.merge_all(found.collect::<Vec<_>>().into_iter())
    }

    pub(super) fn binding(
        &self,
        m: usize,
        binding: &Binding<'a>,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        match binding {
            Binding::Value(value, scope) => self.value(value, m, *scope, depth + 1, active),
            Binding::Class(body, decorators, at) => {
                self.decorated(decorators, (m, *at), Entity::Class(m, *body), depth, active)
            }
            Binding::Function(decorators, at) => {
                self.decorated(decorators, (m, *at), Entity::Clean, depth, active)
            }
            Binding::Inert => Entity::Clean,
            Binding::Import(module, None) => self.module(module),
            Binding::Import(module, Some(name)) => self.member(module, name, depth, active),
            Binding::Unknown => Entity::Unknown,
        }
    }

    pub(super) fn value(
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
            Expr::StringLiteral(text) => clean(self.text(text, depth, active)),
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

    /// The name `name` of module `module`: standard, of the scan, or unknown (third party).
    pub(super) fn member(
        &self,
        module: &str,
        name: &str,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        let full = format!("{module}.{name}");
        if self.written(module, name) {
            return Entity::Unknown;
        }
        if typing_style(module) {
            return Entity::Standard(full);
        }
        if let sub @ Entity::Module(_) = self.module(&full) {
            return sub;
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
            return Entity::Standard(full);
        }
        if top.names.contains_key("__getattr__") && !top.names.contains_key(name) {
            return Entity::Unknown;
        }
        self.name(name, at, 0, depth + 1, active)
    }

    /// Step from an entity to its attribute.
    pub(super) fn step(
        &self,
        base: Entity,
        attr: &str,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        match base {
            Entity::Standard(path) if self.written(&path, attr) => Entity::Unknown,
            Entity::Standard(path) => Entity::Standard(format!("{path}.{attr}")),
            Entity::Module(module) => self.member(&module, attr, depth, active),
            Entity::Class(m, body) => self.attribute(m, body, attr, depth, active),
            Entity::Clean | Entity::Unknown => Entity::Unknown,
        }
    }

    /// True when no metaclass (also by `**kwargs`) can add a data descriptor.
    fn plain_class(&self, m: usize, body: ScopeId, depth: usize, active: &mut Active) -> bool {
        let facts = self.facts(m);
        let scope = &facts.scopes[body];
        let Some(class) = scope.class else {
            return false;
        };
        let keywords = class.arguments.iter().flat_map(|a| &a.keywords);
        let meta = |k: &Keyword| k.arg.as_ref().is_none_or(|n| n.as_str() == "metaclass");
        if keywords.into_iter().any(meta) {
            return false;
        }
        let parent = scope.parent.unwrap_or(0);
        let bases = class.arguments.iter().flat_map(|a| &a.args);
        bases
            .into_iter()
            .all(|base| match self.path(base, m, parent, depth + 1, active) {
                Entity::Standard(_) => true,
                Entity::Class(m2, b2) => {
                    depth < MAX_DEPTH && self.plain_class(m2, b2, depth + 1, active)
                }
                _ => false,
            })
    }

    /// The attribute of a class of the scan: its bindings and every store of the name, else its bases.
    pub(super) fn attribute(
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
        if !self.plain_class(m, body, depth, active) {
            return Entity::Unknown;
        }
        let scope = &facts.scopes[body];
        let own = scope.names.get(attr).into_iter().flatten().map(|b| (m, b));
        let bound: Vec<(usize, &Binding<'a>)> = own.chain(self.stores_of(attr)).collect();
        if !bound.is_empty() {
            let found = bound
                .into_iter()
                .map(|(at, b)| self.binding(at, b, depth, active));
            return self.merge_all(found.collect::<Vec<_>>().into_iter());
        }
        let Some(class) = scope.class else {
            return Entity::Unknown;
        };
        let parent = scope.parent.unwrap_or(0);
        let bases = class.arguments.iter().flat_map(|a| &a.args);
        let found: Vec<Entity> = bases
            .map(|base| match self.path(base, m, parent, depth + 1, active) {
                Entity::Standard(path) => Entity::Standard(format!("{path}.{attr}")),
                Entity::Class(m2, b2) => self.attribute(m2, b2, attr, depth + 1, active),
                _ => Entity::Unknown,
            })
            .collect();
        self.merge_all(found.into_iter())
    }
}
