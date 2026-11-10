// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The syntactic resolver of a site (`_site_resolution`, `_unqualified_candidates`,
//! `_local_import_bindings`).
//!
//! It reads the written names only: the top-level definitions of the module, the named imports of
//! local files and the members of the enclosing class. Python scans the top-level definitions and
//! the definitions of the imported module for each site, and the members of the class for each
//! `this` reference. Here an index of the symbol table answers each question with one lookup.

use std::collections::HashMap;

use archkeel_facts::reply::Target;
use archkeel_wire::reply::Facts;

use crate::definitions::DefinitionKind;
use crate::kept::{Kept, Pending};
use crate::site_syntax::ReceiverKind;
use crate::sites::{Site, SiteKind, SiteUse};
use crate::symbol_table::{Entry, SymbolTable};

/// What a local import binds: `(target module, imported name, namespace, type only)`.
pub type Bound = (String, String, bool, bool);

/// The local imports of each module, by the local name (`_local_import_bindings`).
pub type Imports = HashMap<(String, String), Vec<Bound>>;

/// `_local_import_bindings`: a binding is found by the position of its statement.
pub fn local_imports(pending: &Pending, facts: &Facts) -> Imports {
    let by_site: HashMap<(&str, i64, i64), &str> = pending
        .sites
        .iter()
        .map(|(id, (rel, line, column))| ((rel.as_str(), *line, *column), id.as_str()))
        .collect();
    let targets: HashMap<&str, &Target> = facts
        .imports
        .iter()
        .map(|target| (target.import_id(), target))
        .collect();
    let mut found = Imports::new();
    for rel in &pending.order {
        let Some(kept) = pending.kept.get(rel) else {
            continue;
        };
        for (&(line, column), bindings) in &kept.bindings {
            let edge = by_site.get(&(rel.as_str(), line, column));
            let Some(Target::Local { module, .. }) = edge.and_then(|id| targets.get(id).copied())
            else {
                continue;
            };
            for binding in bindings {
                let key = (kept.module.clone(), binding.local.clone());
                let value = (
                    module.clone(),
                    binding.imported.clone(),
                    binding.namespace,
                    binding.type_only,
                );
                found.entry(key).or_default().push(value);
            }
        }
    }
    found
}

/// What the resolver found for one site.
pub struct Resolved {
    pub candidates: Vec<String>,
    pub status: &'static str,
    pub reason: Option<&'static str>,
}

/// The kinds of definition that a site may name: a reference any, a call a function, a `new` a class.
fn fits(kind: SiteKind, definition: DefinitionKind) -> bool {
    match kind {
        SiteKind::Reference => true,
        SiteKind::Call => definition == DefinitionKind::Function,
        SiteKind::New => definition == DefinitionKind::Class,
    }
}

/// The inputs that the resolution of all sites shares.
pub struct Resolver<'a> {
    pub table: &'a SymbolTable<'a>,
    pub imports: &'a Imports,
}

impl Resolver<'_> {
    /// `_unqualified_candidates`.
    fn unqualified(&self, module: &str, name: &str, site: &Site) -> Vec<String> {
        let mut found: Vec<String> = self
            .table
            .top_named(module, name)
            .filter(|item| fits(site.kind, item.definition.kind))
            .map(|item| format!("{module}.{}", item.definition.name))
            .collect();
        let bound = self.imports.get(&(module.to_owned(), name.to_owned()));
        for (target, imported, namespace, type_only) in bound.into_iter().flatten() {
            if *namespace || (*type_only && site.usage != SiteUse::Type) {
                continue;
            }
            found.extend(
                self.table
                    .named_in(target, imported)
                    .filter(|item| {
                        item.definition.exported && fits(site.kind, item.definition.kind)
                    })
                    .map(|item| format!("{target}.{}", item.definition.name)),
            );
        }
        found
    }

    /// The members that the class around a `this` reference declares.
    fn this_member(&self, scope: &str, name: &str) -> (Vec<String>, Option<&'static str>, bool) {
        let class_scope = scope.rsplit_once('.').map_or("", |(before, _)| before);
        let declared = self
            .table
            .with_qualified(class_scope)
            .filter(|item: &&Entry| {
                matches!(
                    item.definition.kind,
                    DefinitionKind::Class | DefinitionKind::Interface
                ) && self.table.has_member(item, name)
            })
            .count();
        if declared == 0 {
            return (
                Vec::new(),
                Some("receiver member is not declared locally"),
                false,
            );
        }
        (vec![format!("{class_scope}.{name}")], None, declared == 1)
    }

    /// `_site_resolution`, for a site that no script analysis has resolved.
    pub fn resolve(&self, kept: &Kept, module: &str, scope: &str, site: &Site) -> Resolved {
        let name = site.name.map(|text| text.decode(kept.text.as_bytes()));
        let shadowed = name
            .as_deref()
            .is_some_and(|name| kept.shadow.shadows(site.shadow.chain, name));
        let rebound = name
            .as_deref()
            .is_some_and(|name| kept.rebound.contains(name));
        let mut candidates = Vec::new();
        let mut reason = None;
        let mut unique_this = false;
        let named = name.as_deref().filter(|name| !name.is_empty());
        if let (Some(name), false, false, false, false) = (
            named,
            site.computed,
            site.scope_ambiguous,
            shadowed,
            rebound,
        ) {
            if site.receiver.is_none() {
                candidates = self.unqualified(module, name, site);
            } else if site.kind == SiteKind::Reference && site.receiver_kind == ReceiverKind::This {
                (candidates, reason, unique_this) = self.this_member(scope, name);
            } else {
                reason = Some("receiver dispatch is not proven");
            }
        } else if site.computed {
            reason = Some("computed expression is not statically bound");
        } else if site.scope_ambiguous || shadowed {
            reason = Some("lexical binding may shadow the name");
        } else if rebound {
            reason = Some("name is rebound in module scope");
        }
        candidates.sort();
        candidates.dedup();
        let unique = candidates.len() == 1
            && reason.is_none()
            && (unique_this
                || candidates
                    .iter()
                    .all(|target| self.table.count(target) == 1));
        let status = if unique {
            "resolved"
        } else if candidates.is_empty() {
            "unresolved"
        } else {
            "partially_resolved"
        };
        if status == "partially_resolved" && reason.is_none() {
            reason = Some("multiple definition sites share the target name");
        }
        if reason.is_none() && status != "resolved" {
            reason = Some("definition is missing or ambiguous");
        }
        Resolved {
            candidates,
            status,
            reason,
        }
    }
}
