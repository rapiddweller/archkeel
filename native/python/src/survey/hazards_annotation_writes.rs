// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The attributes of standard modules that the scan writes (AD-1175): names from such a module are
//! no longer type forms.

use std::collections::HashMap;

use ruff_python_ast::Expr;

use super::entity::Project;
use super::facts::{Binding, ScopeId, Write};
use super::stdlib::is_stdlib;

impl<'a> Project<'a> {
    /// True when the scan writes the attribute `name` of the module `module` (standard or of the
    /// scan): its names are no longer what the module defines. A write through a receiver that no
    /// import names (`x.name = v` with `x` unknown) counts for every module: it may be one.
    pub(super) fn written(&self, module: &str, name: &str) -> bool {
        let all = self.written.get_or_init(|| {
            let writes = (0..self.modules.len())
                .flat_map(|at| self.facts(at).writes.iter().map(move |w| (at, w)));
            let named =
                writes.filter_map(|(at, w)| Some((self.module_written(at, w), w.attr.clone()?)));
            named.collect()
        });
        let key = |m: &str| (m.to_owned(), name.to_owned());
        all.contains(&key(module)) || all.contains(&key("*"))
    }

    /// The dotted module that all `bindings` name, if they agree.
    fn agree(&self, m: usize, bindings: Vec<&Binding<'a>>, depth: usize) -> Option<String> {
        let paths: Vec<Option<String>> = bindings
            .iter()
            .map(|b| match b {
                Binding::Import(module, None) => Some(module.clone()),
                Binding::Import(module, Some(name)) => Some(format!("{module}.{name}")),
                Binding::Value(value, home) => self.dotted(value, m, *home, depth + 1),
                _ => None,
            })
            .collect();
        let first = paths.first()?.clone()?;
        paths
            .iter()
            .all(|p| p.as_deref() == Some(first.as_str()))
            .then_some(first)
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
                let id = node.id.as_str();
                let holders = facts.holders(scope, id);
                let all = holders.iter().flat_map(|at| &facts.scopes[*at].names[id]);
                self.agree(m, all.collect(), depth)
            }
            _ => None,
        }
    }

    /// The stores of the attribute `attr` in all modules of the scan (`C.attr = v` can stand in a
    /// consumer of `C`), with the module of each.
    pub(super) fn stores_of(&self, attr: &str) -> Vec<(usize, &Binding<'a>)> {
        let index = self.stores.get_or_init(|| {
            let lists = (0..self.modules.len()).flat_map(|at| {
                self.facts(at)
                    .stores
                    .iter()
                    .map(move |(name, list)| (at, name, list))
            });
            let mut found: HashMap<String, Vec<(usize, usize)>> = HashMap::new();
            for (at, name, list) in lists {
                let each = (0..list.len()).map(|i| (at, i));
                found.entry(name.clone()).or_default().extend(each);
            }
            found
        });
        let places = index.get(attr).into_iter().flatten();
        places
            .map(|(at, i)| (*at, &self.facts(*at).stores[attr][*i]))
            .collect()
    }

    /// The module that a write goes to: its dotted name, or `*` when the receiver names no one.
    fn module_written(&self, at: usize, write: &Write<'a>) -> String {
        let Some(path) = self.dotted(write.receiver, at, write.scope, 0) else {
            return "*".to_owned();
        };
        let path = self.canonical(path, 0);
        // `contextlib.os` is the module `os` by a re-export that the table has not read: a
        // standard path of two parts or more names no one module.
        let open = path.contains('.') && !self.by_name.contains_key(path.as_str());
        if open && is_stdlib(&path) {
            "*".to_owned()
        } else {
            path
        }
    }

    /// `app.cfg.alias` where `app.cfg` binds `alias` to a module (`import contextlib as alias`):
    /// the module that the path names in the end.
    fn canonical(&self, path: String, depth: usize) -> String {
        let named = path.rsplit_once('.').and_then(|(module, name)| {
            let at = *self.by_name.get(module)?;
            let facts = self.facts(at);
            let home = facts.holder(0, name)?;
            let bindings = facts.scopes[home].names.get(name)?;
            // Module aliases that disagree name no one module: the write counts for every one.
            let aliases = bindings
                .iter()
                .any(|b| matches!(b, Binding::Import(..) | Binding::Value(..)));
            let agreed = self.agree(at, bindings.iter().collect(), depth + 1);
            agreed.or_else(|| aliases.then(|| "*".to_owned()))
        });
        match named {
            Some(next) if depth < 8 && next != path => self.canonical(next, depth + 1),
            _ => path,
        }
    }
}
