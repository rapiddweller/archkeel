// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The members that a name reaches in a class (AD-796 S2; `_member_bindings`,
//! `_constructor_bindings`, `_inherited_member_bindings`, `_site_members` and `_enclosing_class`
//! of release 4.0.1). A member of a base outside the snapshot has no binding here, so a name that
//! only such a base can declare stays unresolved.

use std::collections::BTreeSet;

use super::{binding_kind, types, Bound, Decl, Resolver};
use crate::collection::types::BindingKind;
use crate::syntax::{Definition, DefinitionKind, Member, MemberKind, Site, SiteUse};

impl Resolver<'_> {
    /// The binding of one member of the class `decl`, named as 4.0.1 names it.
    pub(crate) fn member_bound(&self, decl: &Decl<'_>, owner: &str, member: &Member) -> Bound {
        let kind = binding_kind(&member.kind);
        Bound {
            module: decl.module.to_owned(),
            name: format!("{owner}.{}", member.name),
            kind,
            via_prefix: None,
            id: format!(
                "{}:{}:{}:{}",
                self.identity(decl),
                member.span.start_byte,
                super::word(&member.kind),
                member.name
            ),
            at: decl.at,
            span: member.span.clone(),
        }
    }

    /// The members of the one class `owner` of `module` named `name`, else the literal of an
    /// enum, else an inherited member (`_member_bindings`).
    pub(crate) fn members(
        &self,
        module: &str,
        owner: &str,
        name: &str,
        static_only: bool,
    ) -> Vec<Bound> {
        let [decl] = self.local(module, owner)[..] else {
            return Vec::new();
        };
        let direct: Vec<Bound> = decl
            .definition
            .members
            .iter()
            .filter(|member| member.name == name && (!static_only || member.r#static))
            .map(|member| self.member_bound(&decl, owner, member))
            .collect();
        if !Vec::is_empty(&direct) {
            return direct;
        }
        let definition = decl.definition;
        if definition.kind == DefinitionKind::Enum {
            let literal = definition.enum_members.iter().position(|item| item == name);
            if let Some(span) = literal.and_then(|at| definition.enum_member_spans.get(at)) {
                return vec![Bound {
                    module: module.to_owned(),
                    name: format!("{owner}.{name}"),
                    kind: BindingKind::EnumMember,
                    via_prefix: None,
                    id: format!(
                        "{}:{}:enum_member:{name}",
                        self.identity(&decl),
                        span.start_byte
                    ),
                    at: decl.at,
                    span: span.clone(),
                }];
            }
        }
        if static_only {
            return Vec::new();
        }
        self.inherited(module, definition, name, &BTreeSet::new())
    }

    /// The constructors of the one class `owner` of `module` named `name`
    /// (`_constructor_bindings`).
    pub(crate) fn constructors(&self, module: &str, owner: &str, name: &str) -> Vec<Bound> {
        let [decl] = self.local(module, owner)[..] else {
            return Vec::new();
        };
        let qualified = format!("{owner}.{name}");
        decl.definition
            .members
            .iter()
            .filter(|member| member.kind == MemberKind::Constructor)
            .filter(|member| member.name == name || member.name == qualified)
            .map(|member| Bound {
                name: qualified.clone(),
                kind: BindingKind::Constructor,
                ..self.member_bound(&decl, owner, member)
            })
            .collect()
    }

    /// A member that a mixin or the superclass of `definition` declares, nearest first
    /// (`_inherited_member_bindings`). Only a base of the same module is read.
    pub(crate) fn inherited(
        &self,
        module: &str,
        definition: &Definition,
        name: &str,
        seen: &BTreeSet<String>,
    ) -> Vec<Bound> {
        if seen.contains(&definition.name) {
            return Vec::new();
        }
        let mut seen = seen.clone();
        seen.insert(definition.name.clone());
        let parents = definition
            .with_types
            .iter()
            .rev()
            .chain(&definition.extends);
        for parent_name in parents.filter_map(|text| types::type_name(text)) {
            let [parent] = self.local(module, parent_name)[..] else {
                continue;
            };
            let found: Vec<Bound> = parent
                .definition
                .members
                .iter()
                .filter(|member| member.name == name)
                .map(|member| self.member_bound(&parent, parent_name, member))
                .collect();
            if !Vec::is_empty(&found) {
                return found;
            }
            let nested = self.inherited(module, parent.definition, name, &seen);
            if !Vec::is_empty(&nested) {
                return nested;
            }
        }
        Vec::new()
    }

    /// The innermost class-like declaration of the file at `at` that holds `site`
    /// (`_enclosing_class`).
    pub(crate) fn enclosing<'s>(&'s self, at: usize, site: &Site) -> Option<&'s Definition> {
        let parsed = self.syntax.get(at)?.as_ref()?;
        let position = site.span.start_byte;
        parsed
            .definitions
            .iter()
            .filter(|definition| {
                matches!(
                    definition.kind,
                    DefinitionKind::Class
                        | DefinitionKind::Mixin
                        | DefinitionKind::Enum
                        | DefinitionKind::Extension
                        | DefinitionKind::ExtensionType
                )
            })
            .filter(|definition| {
                definition.span.start_byte <= position && position <= definition.span.end_byte
            })
            .min_by_key(|definition| {
                definition
                    .span
                    .end_byte
                    .saturating_sub(definition.span.start_byte)
            })
    }

    /// The members that the enclosing class of `site` declares itself with the name `name`: the
    /// class scope of Dart, which hides a name of the library (AD-796 S2). 4.0.1 looked at the
    /// library first.
    pub(crate) fn own_members(&self, at: usize, site: &Site, name: &str) -> Vec<Bound> {
        let (Some(module), Some(owner)) = (self.module_for(at), self.enclosing(at, site)) else {
            return Vec::new();
        };
        let Some(decl) = self.declaration(at, owner) else {
            return Vec::new();
        };
        // A constructor is no name of the class scope: `Order()` inside `Order` names the class.
        let members = owner
            .members
            .iter()
            .filter(|member| member.name == name && member.kind != MemberKind::Constructor);
        let mut found: Vec<Bound> = members
            .map(|member| self.member_bound(&decl, &owner.name, member))
            .collect();
        if owner.kind == DefinitionKind::Enum && owner.enum_members.iter().any(|item| item == name)
        {
            found.extend(self.members(module, &owner.name, name, true));
        }
        found
    }
}

/// The bindings that a read does not reach (a setter) or a write does not reach (a getter)
/// (`_site_members`).
pub(crate) fn site_members(site: &Site, bindings: Vec<Bound>) -> Vec<Bound> {
    match site.r#use {
        SiteUse::Read => bindings
            .into_iter()
            .filter(|item| item.kind != BindingKind::Setter)
            .collect(),
        SiteUse::Write => bindings
            .into_iter()
            .filter(|item| item.kind != BindingKind::Getter)
            .collect(),
        SiteUse::Type | SiteUse::ReadWrite | SiteUse::Value => bindings,
    }
}
