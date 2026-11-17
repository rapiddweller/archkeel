// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The declaration that one site reaches (AD-796 S2; `_resolve_site`, `_name_bindings`,
//! `_receiver_bindings`, `_site_result` and the namespace checks of release 4.0.1).
//!
//! An unqualified name looks in the scopes of Dart, in their order: a local binding, then a
//! member that the enclosing class declares itself, then the library and its imports, and only
//! then a member that the class inherits (an implicit `this`). Release 4.0.1 looked at the
//! library before the members of the class.

use std::collections::BTreeSet;

use super::members::site_members;
use super::receivers::one_class;
use super::{types, Bound, Resolver};
use crate::collection::types::{BindingKind, Resolution};
use crate::import_survey::binding::visible;
use crate::syntax::{Site, SiteKind, Visibility};

/// The outcome of one site: its status and its bindings.
pub(crate) type Reached = (Resolution, Vec<Bound>);

const UNKNOWN: Reached = (Resolution::Unknown, Vec::new());

impl Resolver<'_> {
    /// The declarations that `site` of the file at `at` reaches (`_resolve_site`).
    pub(crate) fn site(&self, at: usize, site: &Site) -> Reached {
        let (Some(module), Some(name)) = (
            self.module_for(at),
            site.name.as_deref().filter(|name| !str::is_empty(name)),
        ) else {
            return UNKNOWN;
        };
        let shadowed = |item: &str| site.shadowed_names.iter().any(|shadow| shadow == item);
        let receiver_head = site
            .receiver
            .as_deref()
            .map(|receiver| receiver.split('.').next().unwrap_or(""));
        if receiver_head.is_some_and(shadowed) || (site.receiver.is_none() && shadowed(name)) {
            return UNKNOWN;
        }
        if self.conditional_uncertain(module, site, name) {
            return UNKNOWN;
        }
        if site.kind == SiteKind::Call
            && site.receiver.is_none()
            && self.has_lexical(at, site, name)
        {
            return UNKNOWN;
        }
        if site.kind == SiteKind::Creation {
            return self.constructed(at, site);
        }
        if matches!(
            site.kind,
            SiteKind::Extends | SiteKind::Implements | SiteKind::With | SiteKind::Type
        ) {
            let name = types::type_name(name).unwrap_or(name);
            return result(
                self.named(at, module, name, site.receiver.as_deref()),
                module,
            );
        }
        if site.kind == SiteKind::Reference && site.receiver.is_none() {
            let lexical = self.lexical(at, site, name);
            if !Vec::is_empty(&lexical) {
                return result(lexical, module);
            }
        }
        if let Some(receiver) = site.receiver.as_deref() {
            return self.received(at, module, site, receiver);
        }
        let own = self.own_members(at, site, name);
        let mut bindings = if Vec::is_empty(&own) {
            self.in_library(module, name)
        } else {
            own
        };
        if Vec::is_empty(&bindings) {
            if let Some(owner) = self.enclosing(at, site) {
                bindings = self.members(module, &owner.name, name, false);
            }
        }
        let bindings = site_members(site, bindings);
        if site.kind == SiteKind::Call && bindings.iter().any(Bound::class_like) {
            return self.constructed(at, site);
        }
        result(bindings, module)
    }

    fn received(&self, at: usize, module: &str, site: &Site, receiver: &str) -> Reached {
        let head = receiver.split('.').next().unwrap_or("");
        if site.kind == SiteKind::Call && !self.has_lexical(at, site, head) {
            let construction = self.construction(at, site);
            if construction.bound.is_some() {
                return (
                    construction.status,
                    construction.bound.into_iter().collect(),
                );
            }
        }
        let bindings = self.receiver_bindings(at, module, site, receiver);
        if !Vec::is_empty(&bindings) {
            return result(bindings, module);
        }
        let prefix = receiver.rsplit('.').next().unwrap_or(receiver);
        let filtered =
            self.has_import_prefix(module, prefix) || self.filtered_import(module, receiver);
        if self.has_lexical(at, site, head) || !filtered {
            return UNKNOWN;
        }
        (Resolution::Unresolved, Vec::new())
    }

    fn constructed(&self, at: usize, site: &Site) -> Reached {
        let construction = self.construction(at, site);
        (
            construction.status,
            construction.bound.into_iter().collect(),
        )
    }

    /// `_name_bindings` with a receiver: a name of a prefix, a static member or a constructor of
    /// a class, or a member of the type of a variable.
    pub(crate) fn named(
        &self,
        at: usize,
        module: &str,
        name: &str,
        receiver: Option<&str>,
    ) -> Vec<Bound> {
        let Some(receiver) = receiver else {
            return self.in_library(module, name);
        };
        let prefix = receiver.rsplit('.').next().unwrap_or(receiver);
        let imports = self.imported(module, name, Some(prefix));
        if !Vec::is_empty(&imports) {
            return imports;
        }
        if let Some(owner) = self.type_receiver(module, receiver) {
            return self.statics(&owner, name);
        }
        self.receiver_type(at, receiver, None)
            .map(|owner| self.members(&owner.module, &owner.name, name, false))
            .unwrap_or_default()
    }

    /// The one class, enum or mixin that `name` binds in the library scope of `module`: a
    /// declaration of the library, else an import (AD-796 S2; 4.0.1 read the declarations of the
    /// library only, so a static call through an imported class stayed unresolved).
    fn type_receiver(&self, module: &str, name: &str) -> Option<Bound> {
        let found = self.in_library(module, name);
        let class = one_class(found.clone())?;
        let kind = matches!(
            class.kind,
            BindingKind::Class | BindingKind::Enum | BindingKind::Mixin
        );
        (kind && Vec::len(&found) == 1).then_some(class)
    }

    /// The static members of `owner` named `name`, else its constructors of that name.
    fn statics(&self, owner: &Bound, name: &str) -> Vec<Bound> {
        let found = self.members(&owner.module, &owner.name, name, true);
        if Vec::is_empty(&found) {
            self.constructors(&owner.module, &owner.name, name)
        } else {
            found
        }
    }

    /// The members that the receiver of `site` reaches (`_receiver_bindings`).
    fn receiver_bindings(
        &self,
        at: usize,
        module: &str,
        site: &Site,
        receiver: &str,
    ) -> Vec<Bound> {
        let name = site.name.as_deref().unwrap_or("");
        let head = receiver.split('.').next().unwrap_or("");
        if site.computed || site.shadowed_names.iter().any(|shadow| shadow == head) {
            return Vec::new();
        }
        let constructed = self.constructed_receiver(at, module, site, receiver);
        if !Vec::is_empty(&constructed) {
            return constructed;
        }
        if matches!(receiver, "this" | "super") {
            let Some(owner) = self.enclosing(at, site) else {
                return Vec::new();
            };
            let found = if receiver == "super" {
                self.inherited(module, owner, name, &BTreeSet::new())
            } else {
                self.members(module, &owner.name, name, false)
            };
            return site_members(site, found);
        }
        let parts: Vec<&str> = receiver.split('.').collect();
        if self.has_lexical(at, site, head) {
            let found = self
                .receiver_type(at, head, Some(site))
                .map(|owner| self.members(&owner.module, &owner.name, name, false))
                .unwrap_or_default();
            return site_members(site, found);
        }
        if let [prefix, class] = parts.as_slice() {
            let imported = self.imported(module, class, Some(prefix));
            if let Some(owner) = one_class(imported.clone()).filter(|_| Vec::len(&imported) == 1) {
                let found = self.prefixed_statics(module, &owner, (class, prefix), name);
                return site_members(site, found);
            }
        }
        let prefix = receiver.rsplit('.').next().unwrap_or(receiver);
        let imports = self.imported(module, name, Some(prefix));
        if !Vec::is_empty(&imports) {
            return imports;
        }
        let hidden = !Vec::is_empty(&self.own_members(at, site, receiver));
        if let Some(owner) = self.type_receiver(module, receiver).filter(|_| !hidden) {
            return site_members(site, self.statics(&owner, name));
        }
        let found = self
            .receiver_type(at, receiver, Some(site))
            .map(|owner| self.members(&owner.module, &owner.name, name, false))
            .unwrap_or_default();
        site_members(site, found)
    }

    fn has_import_prefix(&self, module: &str, prefix: &str) -> bool {
        self.imports_of(module)
            .any(|(_, directive)| directive.prefix.as_deref() == Some(prefix))
    }

    /// True when an unprefixed import of a local library hides `name` that the library declares
    /// (`_is_filtered_import_name`).
    fn filtered_import(&self, module: &str, name: &str) -> bool {
        self.imports_of(module)
            .filter(|(_, directive)| directive.prefix.is_none() && !visible(directive, name))
            .flat_map(|(at, directive)| self.targets(at, directive))
            .any(|target| target.at.is_some() && !Vec::is_empty(&self.local(&target.module, name)))
    }

    /// True when a conditional import may bind the name of `site` to different declarations
    /// (`_conditional_site_uncertain`).
    fn conditional_uncertain(&self, module: &str, site: &Site, name: &str) -> bool {
        let Some(receiver) = site.receiver.as_deref() else {
            return self.conditional_import_uncertain(module, name, None);
        };
        let parts: Vec<&str> = receiver.split('.').collect();
        let prefix = parts.first().copied().unwrap_or("");
        if !self.has_import_prefix(module, prefix) {
            return false;
        }
        let symbol = if Vec::len(&parts) == 1 {
            name
        } else {
            parts.last().copied().unwrap_or("")
        };
        self.conditional_import_uncertain(module, symbol, Some(prefix))
    }

    fn conditional_import_uncertain(&self, module: &str, name: &str, prefix: Option<&str>) -> bool {
        let conditional = self.imports_of(module).filter(|(_, directive)| {
            directive.prefix.as_deref() == prefix
                && !Vec::is_empty(&directive.alternatives)
                && visible(directive, name)
        });
        for (at, directive) in conditional {
            let targets = self.targets(at, directive);
            if Vec::len(&targets) < 2 {
                return true;
            }
            let branches: Vec<BTreeSet<(String, String, String)>> = targets
                .iter()
                .map(|target| {
                    target
                        .at
                        .map_or_else(BTreeSet::new, |library| self.branch(library, name))
                })
                .collect();
            if branches.iter().any(BTreeSet::is_empty)
                || branches.windows(2).any(|pair| pair[0] != pair[1])
            {
                return true;
            }
        }
        false
    }
}

impl Resolver<'_> {
    /// The static members of the class `owner` that `prefix.class` names, else its constructors
    /// when each import of the prefix closes the namespace of the class.
    fn prefixed_statics(
        &self,
        module: &str,
        owner: &Bound,
        (class, prefix): (&str, &str),
        name: &str,
    ) -> Vec<Bound> {
        let found = self.members(&owner.module, &owner.name, name, true);
        if Vec::is_empty(&found) && self.constructor_namespace_closed(module, class, prefix) {
            return self.constructors(&owner.module, &owner.name, name);
        }
        found
    }

    /// The declarations that one alternative of a conditional import gives for `name`.
    fn branch(&self, library: usize, name: &str) -> BTreeSet<(String, String, String)> {
        self.exported_from(library, name)
            .into_iter()
            .map(|bound| (bound.module, bound.name, super::word(&bound.kind)))
            .collect()
    }
}

/// The status of a site from its bindings (`_site_result`): one accessible declaration is
/// resolved; a private declaration of another library is not accessible.
pub(crate) fn result(bindings: Vec<Bound>, module: &str) -> Reached {
    let any = !Vec::is_empty(&bindings);
    let accessible: Vec<Bound> = bindings
        .into_iter()
        .filter(|item| {
            Visibility::from_name(&item.name) == Visibility::Public || item.module == module
        })
        .collect();
    let ids: BTreeSet<&str> = accessible
        .iter()
        .map(|item| String::as_str(&item.id))
        .collect();
    if BTreeSet::len(&ids) == 1 {
        return (Resolution::Resolved, accessible);
    }
    if Vec::is_empty(&accessible) {
        return if any {
            UNKNOWN
        } else {
            (Resolution::Unresolved, Vec::new())
        };
    }
    (Resolution::Unknown, accessible)
}

#[cfg(test)]
#[path = "sites_tests.rs"]
mod tests;
