// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The lexical bindings of a site (AD-796 S2; `_has_lexical_binding` and `_lexical_bindings` of
//! release 4.0.1): a local binding or a parameter of the scope of the site.

use super::{Bound, Resolver};
use crate::collection::types::BindingKind;
use crate::syntax::{Site, SiteKind, Syntax};

/// True when `binding` binds a name at `position`: its scope holds the position.
pub(super) fn in_scope(binding: &Site, position: usize) -> bool {
    binding.kind == SiteKind::Binding
        && binding
            .scope_span
            .as_ref()
            .is_some_and(|scope| scope.start_byte <= position && position <= scope.end_byte)
}

/// The name that a binding site binds.
pub(super) fn bound_name(binding: &Site) -> Option<&str> {
    binding.assigned_name.as_deref().or(binding.name.as_deref())
}

impl Resolver<'_> {
    pub(super) fn parsed(&self, at: usize) -> Option<&Syntax> {
        self.syntax.get(at)?.as_ref()
    }

    /// True when a local binding or a parameter of the scope of `site` binds `name`
    /// (`_has_lexical_binding`).
    pub(crate) fn has_lexical(&self, at: usize, site: &Site, name: &str) -> bool {
        let Some(parsed) = self.parsed(at) else {
            return false;
        };
        let position = site.span.start_byte;
        if parsed
            .sites
            .iter()
            .any(|item| in_scope(item, position) && bound_name(item) == Some(name))
        {
            return true;
        }
        let scope = site.scope.as_deref();
        parsed.definitions.iter().any(|definition| {
            (scope == Some(String::as_str(&definition.name))
                && definition.parameters.iter().any(|item| item.name == name))
                || definition.members.iter().any(|member| {
                    scope == Some(String::as_str(&member.name))
                        && member.parameters.iter().any(|item| item.name == name)
                })
        })
    }

    /// The nearest local binding of `name` before `site` (`_lexical_bindings`).
    pub(crate) fn lexical(&self, at: usize, site: &Site, name: &str) -> Vec<Bound> {
        let (Some(parsed), Some(module)) = (self.parsed(at), self.module_for(at)) else {
            return Vec::new();
        };
        let position = site.span.start_byte;
        let chosen = parsed
            .sites
            .iter()
            .filter(|item| {
                bound_name(item) == Some(name)
                    && item.span.start_byte <= position
                    && in_scope(item, position)
            })
            .max_by_key(|item| (item.scope_depth, item.span.start_byte));
        let rel = self.rel(at);
        chosen
            .map(|item| Bound {
                module: module.to_owned(),
                name: name.to_owned(),
                kind: BindingKind::Binding,
                via_prefix: None,
                id: format!("{rel}:{}:binding:{name}", item.span.start_byte),
                at,
                span: item.span.clone(),
            })
            .into_iter()
            .collect()
    }
}
