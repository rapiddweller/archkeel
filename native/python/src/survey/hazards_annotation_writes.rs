// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The attributes of standard modules that the scan writes (AD-1175): names from such a module are
//! no longer type forms.

use ruff_python_ast::Expr;

use super::entity::{typing_style, Project};
use super::facts::{Binding, ScopeId};

impl<'a> Project<'a> {
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
                let at = facts.holder(scope, node.id.as_str())?;
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
