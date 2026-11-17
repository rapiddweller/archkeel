// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type of the receiver of a method call (#1571, AD-804). The scan reads the receiver as a
//! chain (`scan_chains.rs`); this resolver follows the written types of the workspace along it:
//! the type of a parameter, a local or `self`, the declared type of a named field of an exact
//! struct, the written return type of the one member or function that a call reaches, and a fixed
//! table of std methods (`impl_ty.rs`). A type is `Own` only when it is an exact struct or enum
//! of the workspace, and `Std` only when its path names the std type for certain.
//!
//! At the call (`verdict`), after `&`, `&mut`, `Box`, `Rc` and `Arc` are peeled one level at a
//! time: a std type reaches no inherent member of the workspace (an inherent `impl` of a std type
//! is E0116); an own type without a `Deref` impl reaches only its own inherent members, and its
//! one member when type, `self` form, arity and visibility are exact (the rule of AD-383). Any
//! other receiver keeps every gap.

use std::collections::{BTreeMap, BTreeSet};

use super::flow::Foreign;
use super::receivers::{certainly_visible, exact_type, field_of, same_gates, Candidate, Typed};
use crate::definitions::{MethodCall, ReceiverChain, Root, SelfKind, Step, Written};
use crate::modules::{Frame, Index, TypeOf};
use crate::tree::Module;
use paths::{outside_path, prelude_variant, std_path};
use ty::{behind_shared, element, no_workspace, project, std_function, std_method, Std, Ty};

/// What a method call can reach, from the type of its receiver.
pub(super) enum Verdict<'t, 'a> {
    /// No inherent member of the workspace.
    Std,
    /// Only the members of this own type, of the crate of its file, and this one member when it
    /// is certain.
    Own((String, String), usize, Option<&'t Candidate<'a>>),
    Unknown,
}

/// What the resolver reads at one call.
pub(super) struct Context<'t, 'm, 'a> {
    pub(super) index: &'t Index<'a>,
    pub(super) frame: &'t Frame<'a>,
    pub(super) module: &'t Module,
    /// The lexical module of the call.
    pub(super) at: String,
    pub(super) typed: &'t Typed<'a>,
    /// The members that a macro call may define (#1196).
    pub(super) macro_members: &'m BTreeMap<String, BTreeSet<String>>,
    /// No trait of a dependency can be in scope in the file (`impl_scope.rs`).
    pub(super) closed: bool,
}

impl Verdict<'_, '_> {
    /// Whether the call may reach a member of the block. An inherent block of an own type is in
    /// the crate of the type (E0116).
    pub(super) fn keeps(&self, block: &Foreign<'_>) -> bool {
        match (self, &block.ty) {
            (Verdict::Std, _) => false,
            (Verdict::Own((lexical, name), _, _), TypeOf::Known(at, ty)) => {
                at == lexical && ty == name
            }
            (Verdict::Own(_, krate, _), _) => block.module.crate_index == *krate,
            (Verdict::Unknown, _) => true,
        }
    }
}

impl<'t, 'a> Context<'t, '_, 'a> {
    /// The verdict of a method call of the scan.
    pub(super) fn verdict(&self, call: &MethodCall) -> Verdict<'t, 'a> {
        let Some(chain) = call.chain.as_deref() else {
            return Verdict::Unknown;
        };
        let ty = self.chain_type(chain, &call.scope);
        let mut core = &ty;
        while let Ty::Ref(_, inner) = core {
            core = inner;
        }
        while let Ty::Std(Std::Box | Std::Rc | Std::Arc, args) = core {
            let Some(inner) = args.first() else {
                return Verdict::Unknown;
            };
            core = inner;
            while let Ty::Ref(_, inner) = core {
                core = inner;
            }
        }
        match core {
            Ty::Std(..) => Verdict::Std,
            Ty::Own(lexical, name) if !self.typed.derefs.contains(&**name) => {
                // The `self` form of the receiver: the type itself or one written reference.
                let form = match &ty {
                    Ty::Own(..) => Some(SelfKind::Value),
                    Ty::Ref(kind, inner) if matches!(**inner, Ty::Own(..)) => Some(*kind),
                    _ => None,
                };
                let form = form.zip(call.arity).filter(|_| !call.path);
                let member = form.and_then(|form| self.sole((lexical, name), &call.name, form));
                let file = self
                    .index
                    .file_of(lexical)
                    .and_then(|f| self.index.frame(f));
                let Some(file) = file else {
                    return Verdict::Unknown;
                };
                let type_name = (lexical.clone(), name.clone());
                Verdict::Own(type_name, file.module.crate_index, member)
            }
            _ => Verdict::Unknown,
        }
    }

    /// The type of a chain. A chain through a binding of a `fn` with a macro that may bind it again
    /// has no type (AD-524).
    fn chain_type(&self, chain: &ReceiverChain, scope: &[String]) -> Ty {
        if self.module.gated {
            return Ty::Unknown;
        }
        let foreign = (chain.macros.iter()).any(|m| !self.typed.macro_names.contains(m.as_str()));
        let unbound = chain.name == "self" || matches!(chain.root, Root::Literal(_));
        if !unbound && (foreign || self.typed.shadowed_macros) {
            return Ty::Unknown;
        }
        let mut ty = self.root_type(&chain.root, scope);
        // A place behind a shared reference: a `&mut` field of it is only readable (AD-383).
        let mut shared = false;
        for step in &chain.steps {
            if ty == Ty::Unknown {
                break;
            }
            let through = shared || behind_shared(&ty);
            ty = match step {
                Step::Try => match ty {
                    Ty::Std(Std::Result | Std::Option, args) => {
                        args.into_iter().next().unwrap_or(Ty::Unknown)
                    }
                    _ => Ty::Unknown,
                },
                Step::Field(name) => self.field(ty, name),
                Step::Call(name, arity) => self.method(ty, name, *arity),
                Step::Borrow(kind) => Ty::Ref(*kind, Box::new(ty)),
                Step::Variant(name) if prelude_variant(self.frame, name) => {
                    project(ty, |kind, args| match (&**name, kind) {
                        ("Some", Std::Option) | ("Ok", Std::Result) => args.first().cloned(),
                        _ => None,
                    })
                }
                Step::Variant(_) => Ty::Unknown,
                Step::Elem(at) => project(ty, |kind, args| {
                    (kind == Std::Tuple)
                        .then(|| args.get(*at).cloned())
                        .flatten()
                }),
            };
            shared = through && matches!(step, Step::Field(_));
            if shared && matches!(ty, Ty::Ref(SelfKind::Unique, _)) {
                ty = Ty::Ref(SelfKind::Shared, Box::new(ty));
            }
        }
        ty
    }

    fn root_type(&self, root: &Root, scope: &[String]) -> Ty {
        match root {
            Root::Typed(ty) => self.written((self.frame, scope), ty, None),
            Root::Literal("str") => Ty::Ref(SelfKind::Shared, Box::new(Ty::Std(Std::Str, vec![]))),
            Root::Literal(_) => Ty::Std(Std::Prim, vec![]),
            Root::Value(path) => self.value(path, scope),
            Root::Call(path, arity) => self.call(path, *arity, scope),
            Root::Element(of, adapter) => {
                element(&self.chain_type(of, scope), adapter, self.closed)
            }
        }
    }

    /// A written type, read in the file and the scope where it is written. `this` is the type of
    /// `Self` of a member.
    fn written(
        &self,
        (frame, scope): (&Frame<'_>, &[String]),
        ty: &Written,
        this: Option<&Ty>,
    ) -> Ty {
        match ty {
            Written::Ref(kind, inner) => {
                Ty::Ref(*kind, Box::new(self.written((frame, scope), inner, this)))
            }
            Written::Slice(inner) => {
                Ty::Std(Std::Slice, vec![self.written((frame, scope), inner, this)])
            }
            Written::Tuple(elems) => {
                let elems = elems
                    .iter()
                    .map(|elem| self.written((frame, scope), elem, this));
                Ty::Std(Std::Tuple, elems.collect())
            }
            Written::Unknown => Ty::Unknown,
            Written::Path(names, args) if names.first().is_some_and(|first| first == "Self") => {
                match (this, &names[..], &args[..]) {
                    (Some(this), [_], []) => this.clone(),
                    _ => Ty::Unknown,
                }
            }
            Written::Path(names, args) => {
                let args = args
                    .iter()
                    .map(|arg| self.written((frame, scope), arg, this));
                if let Some(std) = std_path(frame, scope, names) {
                    return Ty::Std(std, args.collect());
                }
                if outside_path(frame, scope, names) {
                    // An outside type may deref to a type argument (`Wrapper<T>`).
                    let args: Vec<Ty> = args.collect();
                    return match args.iter().all(no_workspace) {
                        true => Ty::Std(Std::Outside, Vec::new()),
                        false => Ty::Unknown,
                    };
                }
                self.own(frame, scope, names)
            }
        }
    }

    /// An exact struct or enum of the workspace that a path names.
    fn own(&self, frame: &Frame<'_>, scope: &[String], path: &[String]) -> Ty {
        match self.index.type_of(frame, scope, path) {
            TypeOf::Known(lexical, name)
                if exact_type(self.index, self.module, &lexical, &name) =>
            {
                Ty::Own(lexical, name)
            }
            _ => Ty::Unknown,
        }
    }

    /// A named field after auto-deref through references, of an exact struct.
    fn field(&self, ty: Ty, name: &str) -> Ty {
        let mut ty = ty;
        while let Ty::Ref(_, inner) = ty {
            ty = *inner;
        }
        let Ty::Own(lexical, owner) = ty else {
            return Ty::Unknown;
        };
        let found = field_of(
            self.index,
            self.module,
            &self.at,
            (&lexical, &owner, name),
            self.typed,
        );
        found.map_or(Ty::Unknown, |(frame, field)| {
            self.written((frame, &field.scope), &field.written, None)
        })
    }

    /// The type of a method call on a receiver of type `ty`.
    fn method(&self, ty: Ty, name: &str, arity: usize) -> Ty {
        let (form, core) = match ty {
            Ty::Ref(kind, inner) => (kind, *inner),
            other => (SelfKind::Value, other),
        };
        match core {
            Ty::Own(lexical, owner) => {
                let Some(candidate) = self.sole((&lexical, &owner), name, (form, arity)) else {
                    return Ty::Unknown;
                };
                let this = Ty::Own(lexical, owner);
                self.member_type(candidate, &this)
            }
            Ty::Std(..) if !self.typed.trait_members.contains(name) => {
                let ty = match form {
                    SelfKind::Value => core,
                    kind => Ty::Ref(kind, Box::new(core)),
                };
                std_method(&ty, name, arity, self.closed)
            }
            _ => Ty::Unknown,
        }
    }

    /// The written return type of a member, read in the file and the scope of its block.
    fn member_type(&self, candidate: &Candidate<'_>, this: &Ty) -> Ty {
        let Some(frame) = self.index.frame(&candidate.module.module) else {
            return Ty::Unknown;
        };
        self.written((frame, candidate.scope), &candidate.member.ret, Some(this))
    }

    /// The one member `name` of an exact own type that a call reaches for certain: `form` is the
    /// `self` form of the receiver and the arity of a method call (AD-383).
    fn sole(
        &self,
        (lexical, ty): (&str, &str),
        name: &str,
        (kind, arity): (SelfKind, usize),
    ) -> Option<&'t Candidate<'a>> {
        self.member((lexical, ty), name)
            .filter(|c| c.member.kind == Some(kind) && c.member.arity == arity)
    }

    /// The one read member `name` of an exact own type, when it is certain at the call.
    fn member(&self, (lexical, ty): (&str, &str), name: &str) -> Option<&'t Candidate<'a>> {
        let typed = self.typed;
        if typed.unplaced.contains(name)
            || self.macro_members.contains_key(name)
            || !exact_type(self.index, self.module, lexical, ty)
        {
            return None;
        }
        let candidate = typed.named((lexical, ty), name)?;
        let place = (candidate.module, candidate.lexical.as_str());
        let certain = candidate.exact
            && candidate.member.inert
            && same_gates(self.module, candidate.module)
            && certainly_visible(self.module, &self.at, place, &candidate.member.access);
        certain.then_some(candidate)
    }

    /// A struct literal `T { .. }`, or a path `T::V` to a variant of an exact enum.
    fn value(&self, path: &[String], scope: &[String]) -> Ty {
        if let own @ Ty::Own(..) = self.own(self.frame, scope, path) {
            return own;
        }
        self.variant(path, scope)
    }

    /// A path `T::V` or a call `T::V(..)` of a variant `V` of an exact enum `T` that has no member
    /// `V`.
    fn variant(&self, path: &[String], scope: &[String]) -> Ty {
        let Some((last, ty)) = path.split_last() else {
            return Ty::Unknown;
        };
        let Ty::Own(lexical, name) = self.own(self.frame, scope, ty) else {
            return Ty::Unknown;
        };
        // A member of the same name would win over the variant of a path.
        let members = self.typed.by_type.get(&(lexical.clone(), name.clone()));
        let member = (members.into_iter().flatten()).any(|c| c.member.name == *last)
            || self.typed.unplaced.contains(&**last);
        match !member && defs::enum_with(self.index, (&lexical, &name), last) {
            true => Ty::Own(lexical, name),
            false => Ty::Unknown,
        }
    }

    /// A call `f(..)`, `m::f(..)`, `T::f(..)` or `T::V(..)`.
    fn call(&self, path: &[String], arity: usize, scope: &[String]) -> Ty {
        if let ([ty @ .., last], true) = (path, path.len() > 1) {
            if let Some(std) = std_path(self.frame, scope, ty) {
                return std_function(std, last);
            }
            if let Ty::Own(lexical, name) = self.own(self.frame, scope, ty) {
                return self.associated((lexical, name), (last, arity), (path, scope));
            }
        }
        self.function(path, scope)
    }

    /// A path call `T::f(..)` of an exact own type: its one member, or a variant `T::V(..)`.
    fn associated(
        &self,
        (lexical, name): (String, String),
        (last, arity): (&str, usize),
        (path, scope): (&[String], &[String]),
    ) -> Ty {
        let fits = |c: &Candidate<'_>| c.member.arity + usize::from(c.member.receiver) == arity;
        match self.member((&lexical, &name), last) {
            Some(c) if fits(c) => self.member_type(c, &Ty::Own(lexical, name)),
            Some(_) => Ty::Unknown,
            None => self.variant(path, scope),
        }
    }

    /// The written return type of the one free function that a path names.
    fn function(&self, path: &[String], scope: &[String]) -> Ty {
        match defs::function(self.index, self.frame, path, scope) {
            Some((frame, found))
                if same_gates(self.module, frame.module) && !frame.module.gated =>
            {
                self.written((frame, &found.scope), &found.ret, None)
            }
            _ => Ty::Unknown,
        }
    }
}

/// The definitions that a chain names by a path (AD-804).
#[path = "impl_defs.rs"]
mod defs;

/// The std and outside types that a written path names (AD-804).
#[path = "impl_paths.rs"]
mod paths;

/// The receiver types, and the std types and methods that the resolver knows (#1571, AD-804).
#[path = "impl_ty.rs"]
mod ty;

#[cfg(test)]
#[path = "impl_types_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "impl_types_outside_tests.rs"]
mod outside_tests;

#[cfg(test)]
#[path = "impl_types_pattern_tests.rs"]
mod pattern_tests;

#[cfg(test)]
#[path = "impl_types_let_tests.rs"]
mod let_tests;
