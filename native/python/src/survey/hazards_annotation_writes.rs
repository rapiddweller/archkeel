// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The attributes of standard modules that the scan writes (AD-1175): names from such a module are
//! no longer type forms.

use ruff_python_ast::Expr;

use super::entity::Project;
use super::facts::{Binding, ScopeId};

impl<'a> Project<'a> {
    /// True when the scan writes the attribute `name` of the module `module` (standard or of the
    /// scan): its names are no longer what the module defines. A write through a receiver that no
    /// import names (`x.name = v` with `x` unknown) counts for every module: it may be one.
    pub(super) fn written(&self, module: &str, name: &str) -> bool {
        let all = self.written.get_or_init(|| {
            let writes = (0..self.modules.len())
                .flat_map(|at| self.facts(at).writes.iter().map(move |w| (at, w)));
            let named = writes.filter_map(|(at, w)| {
                let attr = w.attr.clone()?;
                match self.dotted(w.receiver, at, w.scope, 0) {
                    Some(path) => Some((path, attr)),
                    None if self.instance(w.receiver, at, w.scope) => None,
                    None => Some(("*".to_owned(), attr)),
                }
            });
            named.collect()
        });
        let key = |m: &str| (m.to_owned(), name.to_owned());
        all.contains(&key(module)) || all.contains(&key("*"))
    }

    /// True when every binding of the receiver is the first parameter of a method.
    fn instance(&self, receiver: &Expr, m: usize, scope: ScopeId) -> bool {
        let Expr::Name(node) = receiver else {
            return false;
        };
        let facts = self.facts(m);
        let id = node.id.as_str();
        let bindings = facts
            .holder(scope, id)
            .map(|at| &facts.scopes[at].names[id]);
        bindings.is_some_and(|b| b.iter().all(|b| matches!(b, Binding::Receiver)))
    }

    /// The dotted name of the module that `receiver` names through its imports or through an
    /// alias of one, if all its bindings agree. It reads no value, so it needs no `written`.
    pub(super) fn dotted(
        &self,
        receiver: &Expr,
        m: usize,
        scope: ScopeId,
        depth: usize,
    ) -> Option<String> {
        if depth > 8 {
            return None;
        }
        match receiver {
            Expr::Attribute(node) => {
                let base = self.dotted(&node.value, m, scope, depth + 1)?;
                Some(format!("{base}.{}", node.attr))
            }
            Expr::Name(node) => {
                let facts = self.facts(m);
                let at = facts.holder(scope, node.id.as_str())?;
                let paths: Vec<Option<String>> = facts.scopes[at].names[node.id.as_str()]
                    .iter()
                    .map(|b| match b {
                        Binding::Import(module, None) => Some(module.clone()),
                        Binding::Import(module, Some(name)) => Some(format!("{module}.{name}")),
                        Binding::Value(value) => self.dotted(value, m, at, depth + 1),
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
