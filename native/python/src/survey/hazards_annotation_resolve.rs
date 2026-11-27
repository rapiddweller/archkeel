// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The resolution of a name or path in the closed-binding rule (AD-1175): the scopes, the imports,
//! the classes and the modules of the scan.

use std::collections::HashSet;

use ruff_python_ast::Expr;

use super::entity::{typing_style, Active, Entity, Project, MAX_BINDINGS, MAX_DEPTH};
use super::facts::{Binding, Facts, Kind, ScopeId};

impl<'a> Project<'a> {
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
        if let Some(at) = self.holder(facts, scope, id) {
            active.push(key);
            let entity = self.merge(m, at, &facts.scopes[at].names[id], depth, active);
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

    /// The scope that binds `id` for code in `scope`: a class scope is read only by its own body.
    pub(super) fn holder(&self, facts: &Facts<'a>, scope: ScopeId, id: &str) -> Option<ScopeId> {
        let chain = std::iter::successors(Some(scope), |at| facts.scopes[*at].parent);
        let mut visible = chain.filter(|at| facts.scopes[*at].kind != Kind::Class || *at == scope);
        visible.find(|at| facts.scopes[*at].names.contains_key(id))
    }

    pub(super) fn merge(
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
    pub(super) fn merge_all(&self, entities: impl Iterator<Item = Entity>) -> Entity {
        let all: Vec<Entity> = entities.collect();
        match all.first() {
            None => Entity::Standard(String::new()),
            Some(_) if all.contains(&Entity::Unknown) => Entity::Unknown,
            Some(first) if all.iter().all(|e| e == first) => first.clone(),
            Some(_) => Entity::Clean,
        }
    }

    pub(super) fn binding(
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

    /// `import m`: a module that the scan holds, or a standard one, or a prefix of one.
    pub(super) fn module(&self, name: &str) -> Entity {
        if typing_style(name) || self.by_name.contains_key(name) {
            return Entity::Module(name.to_owned());
        }
        Entity::Unknown
    }

    /// The name `name` of module `module`: standard (clean), a scanned module (its own binding),
    /// a submodule, or else unknown (a third-party or other standard module: no record proves it).
    pub(super) fn member(
        &self,
        module: &str,
        name: &str,
        depth: usize,
        active: &mut Active,
    ) -> Entity {
        let full = format!("{module}.{name}");
        if typing_style(module) {
            let written = self.written(module, name);
            return if written {
                Entity::Unknown
            } else {
                Entity::Standard(full)
            };
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

    /// The attribute of a class of the scan: its own bindings and every store of that name
    /// (for any receiver), else the attribute of its bases.
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
                Entity::Standard(path) => Entity::Standard(format!("{path}.{attr}")),
                Entity::Class(m2, b2) => self.attribute(m2, b2, attr, depth + 1, active),
                _ => Entity::Unknown,
            })
            .collect();
        self.merge_all(found.into_iter())
    }

    /// True when the scan writes the attribute `name` of the standard module `module`, or any
    /// attribute of it (a computed `setattr`): its names are no longer type forms.
    pub(super) fn written(&self, module: &str, name: &str) -> bool {
        let all = self.written.get_or_init(|| {
            let writes = (0..self.modules.len())
                .flat_map(|at| self.facts(at).writes.iter().map(move |w| (at, w)));
            let named = writes.filter_map(|(at, w)| {
                let path = self.dotted(w.receiver, at, w.scope)?;
                let attr = w.attr.clone().unwrap_or_else(|| "*".to_owned());
                typing_style(&path).then_some((path, attr))
            });
            named.collect()
        });
        all.contains(&(module.to_owned(), name.to_owned()))
            || all.contains(&(module.to_owned(), "*".to_owned()))
    }

    /// The dotted name of the module that `receiver` names through its imports, if all its
    /// bindings are imports of one module. It reads no value, so it needs no `written`.
    pub(super) fn dotted(&self, receiver: &Expr, m: usize, scope: ScopeId) -> Option<String> {
        match receiver {
            Expr::Attribute(node) => Some(format!(
                "{}.{}",
                self.dotted(&node.value, m, scope)?,
                node.attr
            )),
            Expr::Name(node) => {
                let facts = self.facts(m);
                let at = self.holder(facts, scope, node.id.as_str())?;
                let paths: Vec<Option<String>> = facts.scopes[at].names[node.id.as_str()]
                    .iter()
                    .map(|b| match b {
                        Binding::Import(module, None) => Some(module.clone()),
                        Binding::Import(module, Some(name)) => Some(format!("{module}.{name}")),
                        _ => None,
                    })
                    .collect();
                let first = paths.first()?.clone()?;
                paths
                    .iter()
                    .all(|p| p.as_deref() == Some(first.as_str()))
                    .then_some(first)
            }
            _ => None,
        }
    }
}
