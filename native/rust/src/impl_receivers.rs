// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A method call on a plain `self` (AD-383). Rust looks up `recv.m()` step by step: the type of
//! `recv` by value, then `&`, then `&mut`, then the same for each type that a deref gives. At each
//! step an inherent method of the type wins over a trait method. In a method of `impl S`, the
//! first step is the type of `self` as written: `S`, `&S` or `&mut S`. An inherent `m` of `S` whose
//! `self` has the same form matches at that first step, so nothing can come before it: not a
//! trait method, not a deref target. Rust allows one inherent `m` per type, so the call reaches
//! that member and no other one.
//!
//! The call is resolved only when this is certain. Else it keeps each gap of `impl_edges.rs`:
//! - the type of the block is not placed, or the block or the method is not exact;
//! - no exact inherent member `m` of `S` is found (a trait method, a deref target, a macro or a
//!   file that the scan did not read may define it);
//! - the `self` of the member has another form (a trait method can come at an earlier step);
//! - the arity differs, or the member is not certainly visible at the call;
//! - a block whose type the scan cannot place defines a member `m`.

use std::collections::{BTreeMap, BTreeSet};

use crate::builder::Builder;
use crate::definitions::{Access, ImplBlock, Member, MethodCall, SelfKind};
use crate::modules::{inside, Edge, Frame, Index, TypeOf};
use crate::scan::{Reference, Via};
use crate::tokens::NO_BIND_MACROS;
use crate::tree::Module;

/// A member of an inherent `impl` block of a placed type.
pub(super) struct Candidate<'a> {
    module: &'a Module,
    /// The lexical module of the block.
    lexical: String,
    member: &'a Member,
    exact: bool,
}

/// The members of the inherent `impl` blocks of the walk, by the type that the scan places.
#[derive(Default)]
pub(super) struct Typed<'a> {
    by_type: BTreeMap<(String, String), Vec<Candidate<'a>>>,
    /// The names of the members of the blocks whose type the scan cannot place.
    unplaced: BTreeSet<&'a str>,
    /// The last name of each type with a `Deref` or `DerefMut` impl in the workspace.
    derefs: BTreeSet<&'a str>,
    /// A macro, a `use` leaf or an `extern crate` of the workspace may give the name of a macro of
    /// `std` that binds nothing to another macro (AD-524).
    shadowed_macros: bool,
    /// The names of the `macro_rules!` of the workspace.
    macro_names: BTreeSet<&'a str>,
}

impl<'a> Typed<'a> {
    /// Note what a module says of the types and the macros of the workspace (AD-524).
    pub(super) fn note(&mut self, module: &'a Module) {
        let scan = &module.scan;
        for found in &scan.orphans.impls {
            let last = |path: &'a Option<Vec<String>>| path.as_ref()?.last().map(String::as_str);
            if let (Some("Deref" | "DerefMut"), Some(ty)) =
                (last(&found.trait_path), last(&found.self_path))
            {
                self.derefs.insert(ty);
            }
        }
        let defs = scan.macro_defs.iter().map(|def| def.name.as_str());
        self.macro_names.extend(defs);
        let bound = scan.references.iter().filter_map(|r| match &r.via {
            Via::Use { binding, .. } => binding.as_deref(),
            _ => None,
        });
        let silent = |name: &str| NO_BIND_MACROS.contains(&name);
        let hidden = scan.macro_defs.iter().any(|d| silent(&d.name))
            || bound.into_iter().any(silent)
            || !scan.extern_crates.is_empty();
        self.shadowed_macros |= hidden;
    }

    /// Keep each member of a block by its type, or its name when the type is not placed.
    /// `lexical` is the lexical module of the block.
    pub(super) fn place(
        &mut self,
        lexical: String,
        module: &'a Module,
        block: &'a ImplBlock,
        ty: &TypeOf,
    ) {
        let TypeOf::Known(at, name) = ty else {
            self.unplaced
                .extend(block.members.iter().map(|m| m.name.as_str()));
            return;
        };
        let found = self.by_type.entry((at.clone(), name.clone())).or_default();
        found.extend(block.members.iter().map(|member| Candidate {
            module,
            lexical: lexical.clone(),
            member,
            exact: block.exact && !module.gated,
        }));
    }
}

/// Whether the member is visible at the call for certain. A `pub(in path)` is not read.
fn certainly_visible(caller: &Module, at: &str, candidate: &Candidate<'_>) -> bool {
    let same_crate = caller.crate_index == candidate.module.crate_index;
    match &candidate.member.access {
        Access::Public => true,
        Access::Package(text) if text == "pub(crate)" => same_crate,
        Access::Package(text) if text == "pub(super)" => {
            let parent = candidate.lexical.rsplit_once('.').map(|(up, _)| up);
            same_crate && parent.is_some_and(|parent| inside(at, parent))
        }
        Access::Private => same_crate && inside(at, &candidate.lexical),
        Access::Package(_) => false,
    }
}

/// Whether the type is a struct or an enum that every configuration has as written: in a module
/// that no attribute can remove, with only inert attributes, and the only item of its name in its
/// file.
fn exact_type(index: &Index<'_>, lexical: &str, ty: &str) -> bool {
    let frame = index.file_of(lexical).and_then(|file| index.frame(file));
    frame.is_some_and(|frame| {
        let scan = &frame.module.scan;
        !frame.module.gated && scan.exact_types.contains(ty) && scan.counts.get(ty) == Some(&1)
    })
}

/// Resolve a named field from its exact struct, without deref or an ambiguous field.
fn field_type(
    index: &Index<'_>,
    caller: &Module,
    at: &str,
    (lexical, ty, name): (&str, &str, &str),
    found: &Typed<'_>,
) -> Option<(String, String, SelfKind)> {
    if !exact_type(index, lexical, ty) || found.derefs.contains(ty) {
        return None;
    }
    let frame = index.frame(index.file_of(lexical)?)?;
    let fields: Vec<_> = frame
        .module
        .scan
        .fields
        .get(&(ty.to_owned(), name.to_owned()))?
        .iter()
        .filter(|f| frame.lexical_at(&f.scope) == lexical)
        .collect();
    let [field] = fields.as_slice() else {
        return None;
    };
    let same_crate = caller.crate_index == frame.module.crate_index;
    let visible = match &field.access {
        Access::Public => true,
        Access::Package(text) if text == "pub(crate)" => same_crate,
        Access::Package(text) if text == "pub(super)" => lexical
            .rsplit_once('.')
            .is_some_and(|(parent, _)| same_crate && inside(at, parent)),
        Access::Private => same_crate && inside(at, lexical),
        Access::Package(_) => false,
    };
    if !visible {
        return None;
    }
    let TypeOf::Known(lexical, ty) = index.type_of(frame, &field.scope, &field.path) else {
        return None;
    };
    (!found.derefs.contains(ty.as_str())).then_some((lexical, ty, field.kind))
}

impl Builder {
    /// Resolve a call on `self`, or a path `Self::m`: an edge to the module of the one member that
    /// it reaches, and `true`. `false` when the call is not certain: the caller keeps its gaps.
    pub(super) fn self_call(
        &mut self,
        (index, frame): (&Index<'_>, &Frame<'_>),
        module: &Module,
        call: &MethodCall,
        found: &Typed<'_>,
    ) -> bool {
        let Some(on_self) = &call.on_self else {
            return false;
        };
        // A method call has a `self` form and an arity; a path `Self::m` has neither.
        let mut form = match (on_self.kind, call.arity, call.path) {
            (Some(kind), Some(arity), false) => Some((kind, arity)),
            (None, None, true) => None,
            _ => return false,
        };
        // A parameter has a written type; the workspace must give no reason to doubt it (AD-524).
        let parameter = !matches!(on_self.name.as_str(), "self" | "Self");
        let deref = on_self
            .path
            .last()
            .is_some_and(|ty| found.derefs.contains(ty.as_str()));
        // A macro of the `fn` that is no `macro_rules!` of the workspace can bind any name.
        let foreign = (on_self.macros.iter()).any(|m| !found.macro_names.contains(m.as_str()));
        if parameter && (deref || found.shadowed_macros || foreign) {
            return false;
        }
        let TypeOf::Known(mut lexical, mut ty) =
            index.type_of(frame, &on_self.scope, &on_self.path)
        else {
            return false;
        };
        if let Some(field) = &on_self.field {
            let at = frame.lexical_at(&call.scope);
            let Some((target, name, kind)) =
                field_type(index, module, &at, (&lexical, &ty, field), found)
            else {
                return false;
            };
            if kind == SelfKind::Unique && on_self.kind == Some(SelfKind::Shared) {
                return false;
            }
            (lexical, ty) = (target, name);
            form = call.arity.map(|arity| (kind, arity));
        }
        let unplaced = found.unplaced.contains(call.name.as_str())
            || self.macro_members.contains_key(&call.name);
        if unplaced || module.gated || !exact_type(index, &lexical, &ty) {
            return false;
        }
        let members = found.by_type.get(&(lexical, ty)).into_iter().flatten();
        let candidates: Vec<&Candidate<'_>> =
            members.filter(|c| c.member.name == call.name).collect();
        let at = frame.lexical_at(&call.scope);
        let certain = |c: &Candidate<'_>| {
            let fits = form
                .is_none_or(|(kind, arity)| c.member.kind == Some(kind) && c.member.arity == arity);
            c.exact && fits && certainly_visible(module, &at, c)
        };
        // Rust allows one member `m` per type: two read members mean a case that is not certain.
        let [candidate] = candidates.as_slice() else {
            return false;
        };
        if !certain(candidate) {
            return false;
        }
        let root = on_self.name.as_str();
        let path = match call.path {
            true => format!("{root}::{}", call.name),
            false => format!("{root}.{}", call.name),
        };
        let reference = Reference {
            root: root.to_owned(),
            path,
            site: call.site.clone(),
            names: vec![root.to_owned(), call.name.clone()],
            scope: call.scope.clone(),
            via: Via::Path,
            ..Reference::default()
        };
        let edge = Edge {
            module: candidate.module.module.clone(),
            lexical: candidate.lexical.clone(),
            symbol: Some(call.name.clone()),
            level: 0,
        };
        self.module_import(index, module, &reference, &edge);
        true
    }
}

#[cfg(test)]
#[path = "impl_receivers_tests.rs"]
mod tests;
