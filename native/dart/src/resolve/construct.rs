// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The constructor that a call or a creation reaches (AD-796 S2; `resolve_construction`,
//! `_construction_type`, `_declared_constructor` and `_constructed_receiver_bindings` of release
//! 4.0.1). A constructor is proven only from its class and a declared or implicit default; a
//! factory result is not proven, and a private constructor of another library is unknown.

use super::{Bound, Resolver};
use crate::collection::types::{BindingKind, Resolution};
use crate::import_survey::binding::visible;
use crate::import_survey::index::Kind;
use crate::syntax::{MemberKind, Modifier, Site, SiteKind, Visibility};

/// The resolution of one construction (`ConstructionResolution`).
#[derive(Clone, Debug)]
pub(crate) struct Built {
    pub(crate) status: Resolution,
    pub(crate) bound: Option<Bound>,
    pub(crate) reason: Option<&'static str>,
}

fn built(status: Resolution, bound: Option<Bound>, reason: Option<&'static str>) -> Built {
    Built {
        status,
        bound,
        reason,
    }
}

/// The class name, the constructor name and the class bindings of a construction site.
type Constructed = (String, Option<String>, Vec<Bound>);

impl Resolver<'_> {
    /// Infer the static type of a direct, unprefixed, nongeneric generative constructor call.
    pub(crate) fn inferred_constructor_type(
        &self,
        at: usize,
        site: &Site,
        built: &Built,
    ) -> Option<String> {
        if built.status != Resolution::Resolved
            || site.kind != SiteKind::Call
            || site.receiver.is_some()
            || site.computed
            || !self.parsed(at)?.complete
            || self.index.kinds.get(at) != Some(&Kind::Library)
            || !self.parts_complete(at)
        {
            return None;
        }
        let name = site.name.as_deref()?;
        let module = self.module_for(at)?;
        let bindings = self.in_library(module, name);
        let [bound] = bindings.as_slice() else {
            return None;
        };
        if bound.module != module && !self.has_direct_type_import(module, name, &bound.module) {
            return None;
        }
        let declaration = self.by_identity(&bound.module, &bound.id)?;
        let definition = declaration.definition;
        (bound.kind == BindingKind::Class && Vec::is_empty(&definition.type_parameters))
            .then(|| name.to_owned())
    }

    fn has_direct_type_import(&self, module: &str, name: &str, owner: &str) -> bool {
        let mut imports = self
            .imports
            .get(module)
            .into_iter()
            .flatten()
            .filter(|(_, directive)| directive.prefix.is_none() && visible(directive, name));
        imports
            .clone()
            .all(|(_, directive)| Vec::is_empty(&directive.alternatives))
            && imports.any(|(at, directive)| {
                self.targets(*at, directive)
                    .iter()
                    .any(|target| target.at.is_some() && target.module == owner)
            })
    }

    /// The constructor that `site` of the file at `at` reaches (`resolve_construction`).
    pub(crate) fn construction(&self, at: usize, site: &Site) -> Built {
        if !matches!(site.kind, SiteKind::Call | SiteKind::Creation)
            || site.name.as_deref().is_none_or(str::is_empty)
        {
            return built(
                Resolution::Unresolved,
                None,
                Some("site is not a constructor form"),
            );
        }
        let Some(module) = self.module_for(at) else {
            return built(
                Resolution::Unknown,
                None,
                Some("source has no unique library owner"),
            );
        };
        let Some((class_name, constructor, classes)) = self.construction_type(at, module, site)
        else {
            return built(
                Resolution::Unknown,
                None,
                Some("constructor type is not a simple name"),
            );
        };
        let [bound] = classes.as_slice() else {
            return if Vec::is_empty(&classes) {
                built(
                    Resolution::Unresolved,
                    None,
                    Some("no source class binding"),
                )
            } else {
                built(
                    Resolution::Unknown,
                    None,
                    Some("constructor type is ambiguous"),
                )
            };
        };
        let Some(decl) = self.by_identity(&bound.module, &bound.id) else {
            return built(
                Resolution::Unknown,
                None,
                Some("class declaration is incomplete"),
            );
        };
        if !self
            .syntax
            .get(decl.at)
            .and_then(Option::as_ref)
            .is_some_and(|parsed| parsed.complete)
        {
            return built(
                Resolution::Unknown,
                None,
                Some("class source is incomplete"),
            );
        }
        let result = self.declared_constructor(&decl, bound, &class_name, constructor.as_deref());
        let private = result
            .bound
            .as_ref()
            .is_some_and(|item| Visibility::from_name(&item.name) == Visibility::Private);
        if private && decl.module != module {
            return built(
                Resolution::Unknown,
                None,
                Some("private constructor is library-local"),
            );
        }
        result
    }

    /// The class and constructor names of a construction site and the class bindings of the
    /// class name (`_construction_type`).
    pub(crate) fn construction_type(
        &self,
        at: usize,
        module: &str,
        site: &Site,
    ) -> Option<Constructed> {
        let site_name = site.name.as_deref()?;
        let mut constructor = None;
        let mut prefix: Option<String> = None;
        let mut prefixed = Vec::new();
        let class_name = match (&site.kind, site.receiver.as_deref()) {
            (SiteKind::Creation, _) | (_, None) => {
                let mut parts = site_name.split('.');
                let class_name = parts.next().and_then(super::types::type_name)?;
                constructor = parts.next().map(str::to_owned);
                class_name.to_owned()
            }
            (_, Some(receiver)) => {
                prefixed = self
                    .imported(module, site_name, Some(receiver))
                    .into_iter()
                    .filter(Bound::class_like)
                    .collect();
                let parts: Vec<&str> = receiver.split('.').collect();
                if !Vec::is_empty(&prefixed) {
                    prefix = Some(receiver.to_owned());
                    super::types::type_name(site_name)?.to_owned()
                } else if let [first, .., last] = parts.as_slice() {
                    prefix = Some((*first).to_owned());
                    constructor = Some(site_name.to_owned());
                    (*last).to_owned()
                } else {
                    constructor = Some(site_name.to_owned());
                    receiver.to_owned()
                }
            }
        };
        // A local binding or a member of the enclosing class hides a class of the library.
        let hidden = || {
            self.has_lexical(at, site, &class_name)
                || !Vec::is_empty(&self.own_members(at, site, &class_name))
        };
        if prefix.is_none() && hidden() {
            return None;
        }
        let candidates = match &prefix {
            Some(_) if !Vec::is_empty(&prefixed) => prefixed,
            Some(prefix) => self.imported(module, &class_name, Some(prefix)),
            None => self.in_library(module, &class_name),
        };
        let classes = candidates.into_iter().filter(Bound::class_like).collect();
        Some((class_name, constructor, classes))
    }

    /// The declared or implicit constructor of a class (`_declared_constructor`).
    fn declared_constructor(
        &self,
        decl: &super::Decl<'_>,
        bound: &Bound,
        class_name: &str,
        requested: Option<&str>,
    ) -> Built {
        let definition = decl.definition;
        let constructors: Vec<&crate::syntax::Member> = definition
            .members
            .iter()
            .filter(|item| item.kind == MemberKind::Constructor)
            .collect();
        let abstract_class = definition.modifiers.contains(&Modifier::Abstract);
        if requested.is_none() && Vec::is_empty(&constructors) {
            return self.implicit_constructor(decl, bound, class_name, abstract_class);
        }
        let matches: Vec<&crate::syntax::Member> = match requested {
            None => {
                let dotted = format!("{class_name}.");
                constructors
                    .into_iter()
                    .filter(|item| item.name == class_name || item.name == dotted)
                    .collect()
            }
            Some(requested) => {
                let qualified = format!("{class_name}.{requested}");
                constructors
                    .into_iter()
                    .filter(|item| item.name == requested || item.name == qualified)
                    .collect()
            }
        };
        let [member] = matches.as_slice() else {
            return if Vec::len(&matches) > 1 {
                built(
                    Resolution::Unknown,
                    None,
                    Some("constructor declaration is ambiguous"),
                )
            } else {
                built(
                    Resolution::Unresolved,
                    None,
                    Some("constructor is not declared"),
                )
            };
        };
        if abstract_class && !member.factory {
            return built(
                Resolution::Unresolved,
                None,
                Some("abstract class has no constructible generative constructor"),
            );
        }
        let short = member.name.rsplit('.').next().unwrap_or(&member.name);
        let resolved = Bound {
            name: format!("{class_name}.{short}"),
            kind: BindingKind::Constructor,
            via_prefix: bound.via_prefix.clone(),
            id: format!(
                "{}:{}:constructor:{}",
                self.identity(decl),
                member.span.start_byte,
                member.name
            ),
            ..self.member_bound(decl, class_name, member)
        };
        if member.factory {
            return built(
                Resolution::Unknown,
                Some(resolved),
                Some("factory result is not source-proven"),
            );
        }
        built(Resolution::Resolved, Some(resolved), None)
    }

    /// The implicit default constructor of a class without a constructor.
    fn implicit_constructor(
        &self,
        decl: &super::Decl<'_>,
        bound: &Bound,
        class_name: &str,
        abstract_class: bool,
    ) -> Built {
        if abstract_class {
            return built(
                Resolution::Unresolved,
                None,
                Some("abstract class has no constructible default"),
            );
        }
        let implicit = Bound {
            module: decl.module.to_owned(),
            name: class_name.to_owned(),
            kind: BindingKind::ImplicitConstructor,
            via_prefix: bound.via_prefix.clone(),
            id: format!("{}:implicit-constructor", self.identity(decl)),
            at: decl.at,
            span: decl.definition.span.clone(),
        };
        built(Resolution::Resolved, Some(implicit), None)
    }

    /// The members named like `site` of the class that the one call in its receiver constructs
    /// (`_constructed_receiver_bindings`).
    pub(crate) fn constructed_receiver(
        &self,
        at: usize,
        module: &str,
        site: &Site,
        receiver: &str,
    ) -> Vec<Bound> {
        let Some(parsed) = self.syntax.get(at).and_then(Option::as_ref) else {
            return Vec::new();
        };
        let mut calls = parsed.sites.iter().filter(|item| {
            item.kind == SiteKind::Call
                && item.expression == receiver
                && item.span.start_byte == site.span.start_byte
                && item.span.end_byte <= site.span.end_byte
                && item.scope_span == site.scope_span
        });
        let (Some(call), None) = (calls.next(), calls.next()) else {
            return Vec::new();
        };
        let Some((_, _, classes)) = self.construction_type(at, module, call) else {
            return Vec::new();
        };
        let mut found = Vec::new();
        for candidate in classes {
            let Some(decl) = self.by_identity(&candidate.module, &candidate.id) else {
                continue;
            };
            let members = decl
                .definition
                .members
                .iter()
                .filter(|member| site.name.as_deref() == Some(String::as_str(&member.name)));
            found.extend(members.map(|member| Bound {
                via_prefix: candidate.via_prefix.clone(),
                ..self.member_bound(&decl, &decl.definition.name, member)
            }));
        }
        found
    }
}
