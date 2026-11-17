// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The static type of a receiver (AD-796 S2; `_receiver_type`, `_receiver_annotation`,
//! `_callback_parameter_annotation`, `_inferred_constructor_type` and
//! `_declared_receiver_annotation` of release 4.0.1). The type of a receiver is the type that the
//! source writes, or the class of a constructor that initializes it. Any other type is unknown.

use super::lexical::{bound_name, in_scope};
use super::{types, Bound, Resolver};
use crate::collection::types::Resolution;
use crate::syntax::{Site, SiteKind, Syntax};

/// The builtin types that give no receiver class.
const NO_CLASS: [&str; 3] = ["dynamic", "Object", "void"];

impl Resolver<'_> {
    /// The one class that the static type of `receiver` names (`_receiver_type`).
    pub(crate) fn receiver_type(
        &self,
        at: usize,
        receiver: &str,
        use_site: Option<&Site>,
    ) -> Option<Bound> {
        let (Some(parsed), Some(module)) = (self.parsed(at), self.module_for(at)) else {
            return None;
        };
        if !types::is_name(receiver) {
            return None;
        }
        let annotation = self
            .receiver_annotation(at, parsed, receiver, use_site)
            .unwrap_or_default();
        let text = annotation
            .split('<')
            .next()
            .unwrap_or("")
            .trim()
            .trim_end_matches('?');
        let parts: Vec<&str> = text.split('.').collect();
        let type_name = *parts.last()?;
        if NO_CLASS.contains(&type_name) {
            return None;
        }
        let bindings = match parts.as_slice() {
            [prefix, _, ..] => self.imported(module, type_name, Some(prefix)),
            _ => self.in_library(module, type_name),
        };
        one_class(bindings)
    }

    fn receiver_annotation(
        &self,
        at: usize,
        parsed: &Syntax,
        receiver: &str,
        use_site: Option<&Site>,
    ) -> Option<String> {
        let visible = parsed.sites.iter().filter(|binding| {
            binding.kind == SiteKind::Binding
                && bound_name(binding) == Some(receiver)
                && binding.scope_span.is_some()
                && use_site.is_none_or(|site| {
                    binding.span.start_byte < site.span.start_byte
                        && in_scope(binding, site.span.start_byte)
                })
        });
        let Some(chosen) = visible.max_by_key(|item| (item.scope_depth, item.span.start_byte))
        else {
            return use_site.and_then(|site| declared_annotation(parsed, receiver, site));
        };
        let mut annotation = chosen.assignment_annotation.clone();
        if annotation.is_none() && chosen.initializer.is_some() {
            annotation = self.inferred_type(at, parsed, chosen);
        }
        if annotation.is_none() && use_site.is_some() {
            annotation = self.callback_parameter(at, parsed, chosen);
        }
        annotation
    }

    /// The element type of the second parameter of a `fold` callback over a `List` or an
    /// `Iterable` of `dart:core` (`_callback_parameter_annotation`).
    fn callback_parameter(&self, at: usize, parsed: &Syntax, binding: &Site) -> Option<String> {
        let scope = binding.scope_span.as_ref()?;
        let mut calls = parsed.sites.iter().filter(|item| {
            item.kind == SiteKind::Call
                && item.name.as_deref() == Some("fold")
                && item.receiver.is_some()
                && item.span.start_byte <= scope.start_byte
                && scope.end_byte <= item.span.end_byte
                && Vec::len(&item.arguments) == 2
        });
        let (Some(call), None) = (calls.next(), calls.next()) else {
            return None;
        };
        let mut siblings: Vec<&Site> = parsed
            .sites
            .iter()
            .filter(|item| {
                item.kind == SiteKind::Binding
                    && item.scope_span.as_ref().is_some_and(|other| {
                        other.start_byte == scope.start_byte && other.end_byte == scope.end_byte
                    })
            })
            .collect();
        siblings.sort_by_key(|item| item.span.start_byte);
        if !matches!(siblings.as_slice(), [_, second] if std::ptr::eq(*second, binding)) {
            return None;
        }
        let collection =
            self.receiver_annotation(at, parsed, call.receiver.as_deref()?, Some(call))?;
        let (name, arguments) = collection.split_once('<')?;
        let name = name.trim();
        let module = self.module_for(at)?;
        if !matches!(name, "List" | "Iterable")
            || !arguments.ends_with('>')
            || !Vec::is_empty(&self.local(module, name))
            || !Vec::is_empty(&self.imported(module, name, None))
        {
            return None;
        }
        let element = arguments
            .get(..str::len(arguments).saturating_sub(1))?
            .trim();
        (!str::is_empty(element) && element != "dynamic" && element != "Object?")
            .then(|| element.to_owned())
    }

    /// The class of the one constructor call that initializes `binding`
    /// (`_inferred_constructor_type`).
    fn inferred_type(&self, at: usize, parsed: &Syntax, binding: &Site) -> Option<String> {
        let initializer = binding.initializer.as_deref()?;
        let mut candidates = parsed.sites.iter().filter(|item| {
            item.kind == SiteKind::Call
                && item.expression == initializer
                && binding.span.start_byte <= item.span.start_byte
                && item.span.end_byte <= binding.span.end_byte
        });
        let (Some(site), None) = (candidates.next(), candidates.next()) else {
            return None;
        };
        if site
            .name
            .as_deref()
            .is_some_and(|name| self.has_lexical(at, site, name))
        {
            return None;
        }
        let resolution = self.construction(at, site);
        if resolution.status != Resolution::Resolved {
            return None;
        }
        let binding = resolution.bound?;
        Some(binding.name.split('.').next().unwrap_or("").to_owned())
    }
}

/// The one class of `bindings`, by declaration.
pub(crate) fn one_class(bindings: Vec<Bound>) -> Option<Bound> {
    let mut classes = bindings.into_iter().filter(Bound::class_like);
    let first = classes.next()?;
    classes.all(|other| other.id == first.id).then_some(first)
}

/// The written type of a parameter or a field named `receiver` that holds `site`
/// (`_declared_receiver_annotation`).
fn declared_annotation(parsed: &Syntax, receiver: &str, site: &Site) -> Option<String> {
    let position = site.span.start_byte;
    let scope = site.scope.as_deref();
    let mut holders: Vec<&crate::syntax::Definition> = parsed
        .definitions
        .iter()
        .filter(|item| {
            item.span.start_byte <= position
                && (item.span.end_byte >= position || scope == Some(String::as_str(&item.name)))
        })
        .collect();
    holders.sort_by_key(|item| item.span.end_byte.saturating_sub(item.span.start_byte));
    for definition in holders {
        if let Some(parameter) = definition
            .parameters
            .iter()
            .find(|item| item.name == receiver)
        {
            return parameter.annotation.clone();
        }
        let members = definition.members.iter().filter(|member| {
            member.span.start_byte <= position
                && (member.span.end_byte >= position || scope == Some(String::as_str(&member.name)))
        });
        for member in members {
            if let Some(parameter) = member.parameters.iter().find(|item| item.name == receiver) {
                return parameter.annotation.clone();
            }
        }
        if let Some(field) = definition.members.iter().find(|item| item.name == receiver) {
            return field.annotation.clone();
        }
    }
    None
}
