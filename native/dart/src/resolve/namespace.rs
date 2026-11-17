// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that the imports and exports of a library bind (AD-796; `_imported_bindings`,
//! `_exported_bindings`, `resolve_name` and `_class_for_type` of release 4.0.1).

use std::collections::{BTreeMap, BTreeSet};

use super::{class_like, types, Bound, Decl, Resolver, Substitutions};
use crate::import_survey::binding::visible;
use crate::syntax::{Directive, Visibility};

impl<'a> Resolver<'a> {
    /// Each declaration that the imports of `module` with `prefix` bind to `name`, by identity
    /// (`_imported_bindings`).
    pub(crate) fn imported(&self, module: &str, name: &str, prefix: Option<&str>) -> Vec<Bound> {
        let mut unique: BTreeMap<String, Bound> = BTreeMap::new();
        let bindings = self
            .imports
            .get(module)
            .into_iter()
            .flatten()
            .filter(|(_, directive)| {
                directive.prefix.as_deref() == prefix && visible(directive, name)
            })
            .flat_map(|(at, directive)| self.targets(*at, directive))
            .filter_map(|target| target.at)
            .flat_map(|library| self.exported(library, name, &mut BTreeSet::new(), prefix));
        for bound in bindings {
            unique.entry(bound.id.clone()).or_insert(bound);
        }
        unique.into_values().collect()
    }

    /// The declarations that the library at `at` exports as `name` (`_exported_bindings`): its
    /// own public declaration, else each one that an `export` passes on.
    fn exported(
        &self,
        at: usize,
        name: &str,
        seen: &mut BTreeSet<String>,
        prefix: Option<&str>,
    ) -> Vec<Bound> {
        let Some(module) = self.module_for(at) else {
            return Vec::new();
        };
        if !seen.insert(module.to_owned()) {
            return Vec::new();
        }
        let direct: Vec<Bound> = self
            .local(module, name)
            .iter()
            .filter(|decl| decl.definition.visibility == crate::syntax::Visibility::Public)
            .map(|decl| self.bound(decl, prefix))
            .collect();
        if !Vec::is_empty(&direct) {
            return direct;
        }
        let exports = self.exports.get(module).into_iter().flatten();
        exports
            .filter(|(_, directive)| visible(directive, name))
            .flat_map(|(from, directive)| self.targets(*from, directive))
            .filter_map(|target| target.at)
            .flat_map(|library| self.exported(library, name, &mut seen.clone(), prefix))
            .collect()
    }

    /// The declarations that `name` binds in the library scope of `module` (`_name_bindings`
    /// without a receiver): a declaration of the library, else an unprefixed import.
    pub(crate) fn in_library(&self, module: &str, name: &str) -> Vec<Bound> {
        let local = self.local(module, name);
        if Vec::is_empty(&local) {
            self.imported(module, name, None)
        } else {
            local.iter().map(|decl| self.bound(decl, None)).collect()
        }
    }

    /// The qualified names that the type text `name` binds in the file at `at` (`resolve_name`).
    pub(crate) fn resolve_name(&self, at: usize, name: &str) -> Vec<String> {
        let (Some(module), Some((prefix, type_name))) = (self.module_for(at), types::nominal(name))
        else {
            return Vec::new();
        };
        if prefix.is_none() {
            let local = self.local(module, type_name);
            if !Vec::is_empty(&local) {
                let mut names: Vec<String> = local
                    .iter()
                    .map(|decl| format!("{}.{}", decl.module, decl.definition.name))
                    .collect();
                names.sort();
                return names;
            }
        }
        let mut names: Vec<String> = self
            .imported(module, type_name, prefix)
            .iter()
            .map(|bound| format!("{}.{}", bound.module, bound.name))
            .collect();
        names.sort();
        names
    }

    /// The one class-like declaration that a type text names, with the substitution of its type
    /// parameters and the constructor name that the text adds (`_class_for_type`).
    pub(crate) fn class_for_type(
        &self,
        module: &str,
        text: &str,
    ) -> Option<(Decl<'a>, Substitutions, Option<String>)> {
        let raw = text.trim();
        let head = raw.split('<').next().unwrap_or("");
        let parts: Vec<&str> = head.split('.').collect();
        let mut name = *parts.first()?;
        let mut constructor = None;
        let mut prefix = None;
        let local_classes = || {
            self.local(module, parts[0])
                .iter()
                .filter(|decl| class_like(decl.definition.kind))
                .count()
        };
        match parts.as_slice() {
            [_] => {}
            [_, second, ..] if local_classes() == 1 => constructor = Some((*second).to_owned()),
            [first, second] => (prefix, name) = (Some(*first), *second),
            [first, second, third] => {
                (prefix, name) = (Some(*first), *second);
                constructor = Some((*third).to_owned());
            }
            _ => return None,
        }
        let bindings = match prefix {
            Some(prefix) => self.imported(module, name, Some(prefix)),
            None => self.in_library(module, name),
        };
        let classes: Vec<&Bound> = bindings.iter().filter(|bound| bound.class_like()).collect();
        let ids: BTreeSet<&str> = classes
            .iter()
            .map(|bound| String::as_str(&bound.id))
            .collect();
        if BTreeSet::len(&ids) != 1 {
            return None;
        }
        let bound = classes.first()?;
        let decl = self.by_identity(&bound.module, &bound.id)?;
        let arguments = raw
            .split_once('<')
            .and_then(|(_, rest)| rest.rsplit_once('>'))
            .map_or("", |(inside, _)| inside);
        let actuals = if str::is_empty(arguments) {
            Vec::new()
        } else {
            types::split(arguments)
        };
        let substitutions = decl
            .definition
            .type_parameters
            .iter()
            .cloned()
            .zip(actuals)
            .collect();
        Some((decl, substitutions, constructor))
    }

    /// Each import directive of `module` with the source index of its file.
    pub(crate) fn imports_of(
        &self,
        module: &str,
    ) -> impl Iterator<Item = (usize, &'a Directive)> + '_ {
        self.imports.get(module).into_iter().flatten().copied()
    }

    /// The declarations that the library at `at` exports as `name`.
    pub(crate) fn exported_from(&self, at: usize, name: &str) -> Vec<Bound> {
        self.exported(at, name, &mut BTreeSet::new(), None)
    }

    /// True when each import of `module` with `prefix` that lets `name` through has a closed
    /// export namespace for it (`_constructor_namespace_closed`).
    pub(crate) fn constructor_namespace_closed(
        &self,
        module: &str,
        name: &str,
        prefix: &str,
    ) -> bool {
        self.imports_of(module)
            .filter(|(_, directive)| {
                directive.prefix.as_deref() == Some(prefix) && visible(directive, name)
            })
            .all(|(at, directive)| self.directive_closed(at, directive, name, &BTreeSet::new()))
    }

    /// True when the library at `at` and its parts are read in full and each export that lets
    /// `name` through is closed (`_export_namespace_closed`).
    fn export_closed(&self, at: usize, name: &str, seen: &BTreeSet<String>) -> bool {
        let complete = |file: usize| {
            self.syntax
                .get(file)
                .and_then(Option::as_ref)
                .is_some_and(|parsed| parsed.complete)
        };
        let Some(module) = self.module_for(at) else {
            return false;
        };
        if !complete(at)
            || self
                .parts
                .get(&at)
                .into_iter()
                .flatten()
                .any(|part| !complete(*part))
        {
            return false;
        }
        if seen.contains(module) {
            return true;
        }
        let declared = self.local(module, name);
        if declared
            .iter()
            .any(|decl| decl.definition.visibility == Visibility::Public)
        {
            return true;
        }
        let mut inner = seen.clone();
        inner.insert(module.to_owned());
        self.exports
            .get(module)
            .into_iter()
            .flatten()
            .filter(|(_, directive)| visible(directive, name))
            .all(|(from, directive)| self.directive_closed(*from, directive, name, &inner))
    }

    /// True when each URI of `directive` gives a closed library, and each alternative gives the
    /// same declarations (`_directive_namespace_closed`).
    fn directive_closed(
        &self,
        at: usize,
        directive: &Directive,
        name: &str,
        seen: &BTreeSet<String>,
    ) -> bool {
        let importer = self.rel(at);
        let alternatives = directive
            .alternatives
            .iter()
            .map(|(_, uri)| Some(String::as_str(uri)));
        let mut previous: Option<BTreeSet<String>> = None;
        for uri in std::iter::once(directive.target.as_deref()).chain(alternatives) {
            let Some(library) = uri
                .and_then(|uri| self.target(importer, uri))
                .and_then(|target| target.at)
            else {
                return false;
            };
            if !self.export_closed(library, name, seen) {
                return false;
            }
            if Vec::is_empty(&directive.alternatives) {
                continue;
            }
            let ids: BTreeSet<String> = self
                .exported(library, name, &mut seen.clone(), None)
                .into_iter()
                .map(|bound| bound.id)
                .collect();
            if previous.as_ref().is_some_and(|before| *before != ids) {
                return false;
            }
            previous = Some(ids);
        }
        true
    }
}
