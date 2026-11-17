// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed parameters of a `fn` (AD-524). A parameter `x: T`, `x: &T` or `x: &mut T` with a
//! plain identifier and a plain path has the type that is written, so a call `x.m()` has the
//! same first step as a call on `self` (AD-383): the written type, and the kind of the written
//! reference. A written type is a proof; inference is not.
//!
//! A parameter has a proof only when its name is bound once in the `fn`: the parameter. Any other
//! binding is a refusal: a `let`, a pattern of a `match`, `if let`, `while let` or `for`, a
//! parameter of a closure or of a nested `fn`, an item of that name, a `use` that may bind it,
//! and a macro call whose tokens name it (a macro can bind a name that its call passes), except
//! the macros of `std` that bind nothing. A type that names a generic parameter of the `fn` or of
//! the `impl` is generic, so it is not read. The resolution of the type, its exactness and the
//! member are the checks of `impl_receivers.rs`.
//!
//! #1571 (AD-804): each binding with a proof also keeps its origin, the receiver chain that the
//! name stands for: the written type of a parameter, of a typed local or of a typed closure
//! parameter (with its type arguments), or the chain of the initializer of an untyped top-level
//! local. `impl_types.rs` resolves it.

use std::collections::{BTreeMap, BTreeSet};

use syn::visit::{self, Visit};
use syn::{
    Attribute, FnArg, GenericArgument, GenericParam, Item, Pat, PathArguments, Signature, Type,
};

use super::bodies::{Binder, Bodies};
use super::chains::{chain_of, destructure, Names};
use super::sites::ClosureSites;
use super::written_types::{with_self, written};
use crate::definitions::{OnSelf, ReceiverChain, Root, SelfKind, Written};
use crate::tokens::plain;
pub(in crate::scan) use bound::item_name;
use bound::Bound;

/// How a `fn` binds names.
#[path = "scan_bound.rs"]
mod bound;

/// Whether a generic argument binds a type or a const: a lifetime does not change which
/// inherent methods a type has.
fn binds_type(argument: &GenericArgument) -> bool {
    !matches!(argument, GenericArgument::Lifetime(_))
}

/// The segments of a plain relative type path: no qualified self, no leading `::`, and no type
/// or const argument (a lifetime does not change which inherent methods a type has).
pub(super) fn plain_path(ty: &Type) -> Option<Vec<String>> {
    let Type::Path(path) = ty else {
        return None;
    };
    if path.qself.is_some() || path.path.leading_colon.is_some() {
        return None;
    }
    let mut names = Vec::new();
    for segment in &path.path.segments {
        match &segment.arguments {
            PathArguments::None => {}
            PathArguments::AngleBracketed(list) if !list.args.iter().any(binds_type) => {}
            _ => return None,
        }
        names.push(plain(&segment.ident));
    }
    Some(names)
}

/// The name of a type or const parameter. A lifetime has none.
pub(super) fn generic_name(param: &GenericParam) -> Option<String> {
    match param {
        GenericParam::Type(found) => Some(plain(&found.ident)),
        GenericParam::Const(found) => Some(plain(&found.ident)),
        GenericParam::Lifetime(_) => None,
    }
}

/// Where a binding holds: after a place, and only at some sites.
type Place = (Option<(usize, usize)>, Option<BTreeSet<(usize, usize)>>);

#[derive(Debug)]
struct Binding {
    /// The plain written type (AD-524), or `None` for another form.
    receiver: Option<OnSelf>,
    /// The chain that the name stands for (#1571).
    origin: Option<ReceiverChain>,
    after: Option<(usize, usize)>,
    sites: Option<BTreeSet<(usize, usize)>>,
}

impl Binding {
    fn new(
        name: &str,
        typed: Option<(Vec<String>, SelfKind)>,
        origin: Option<ReceiverChain>,
        (scope, bound): (&[String], &Bound),
        (after, sites): Place,
    ) -> Self {
        let receiver = typed.map(|(path, kind)| OnSelf {
            name: name.to_owned(),
            path,
            scope: scope.to_vec(),
            kind: Some(kind),
            macros: bound.macros.iter().cloned().collect(),
            fields: Vec::new(),
        });
        Self {
            receiver,
            origin,
            after,
            sites,
        }
    }

    fn seen(&self, at: (usize, usize)) -> bool {
        self.after.is_none_or(|after| at > after)
            && self.sites.as_ref().is_none_or(|sites| sites.contains(&at))
    }
}

/// The bindings of one `fn` that have a proof, by name, and what the chains of the `fn` need.
#[derive(Debug, Default)]
pub(super) struct Params {
    /// A parameter or a local has one binding; closures and loops may bind a name once each, at
    /// disjoint sites.
    found: BTreeMap<String, Vec<Binding>>,
    /// No attribute that is not inert and no nested macro call is in the `fn`.
    proved: bool,
    /// Each name that the `fn` binds or that a `use` or a macro call of it may bind, and the type
    /// parameters in scope.
    hide: BTreeSet<String>,
    /// The macros of the `fn` that are no silent macro of `std`.
    macros: Vec<String>,
    /// The chain of `self` in a method of an exact block, and the exact path of `Self`.
    this: Option<ReceiverChain>,
    self_type: Option<Vec<String>>,
}

impl Params {
    /// The bindings of a `fn` without a proof: only `self` keeps its chain.
    pub(super) fn bare(this: Option<ReceiverChain>) -> Self {
        Self {
            this,
            ..Self::default()
        }
    }

    pub(super) fn get(&self, name: &str, at: (usize, usize)) -> Option<&OnSelf> {
        let found = self.binding(name, at)?;
        found.receiver.as_ref()
    }

    fn binding(&self, name: &str, at: (usize, usize)) -> Option<&Binding> {
        self.found.get(name)?.iter().find(|found| found.seen(at))
    }

    fn bind(&mut self, name: String, binding: Binding) {
        self.found.entry(name).or_default().push(binding);
    }

    /// A type that the body writes, or `None` when an item or a macro of the body may hide a
    /// name of it, or `Self` has no exact type.
    fn body_type(&self, ty: &Type) -> Option<Written> {
        fn hidden(ty: &Written, params: &Params) -> bool {
            match ty {
                Written::Path(names, args) => {
                    let first = names.first().map_or("", String::as_str);
                    let ours = matches!(first, "crate" | "self" | "super" | "Self");
                    params.hide.contains(first)
                        || (!params.macros.is_empty() && !ours)
                        || args.iter().any(|arg| hidden(arg, params))
                }
                Written::Ref(_, inner) | Written::Slice(inner) => hidden(inner, params),
                Written::Tuple(elems) => elems.iter().any(|elem| hidden(elem, params)),
                Written::Unknown => false,
            }
        }
        let found = with_self(written(ty, &self.hide), self.self_type.as_deref());
        (!hidden(&found, self)).then_some(found)
    }

    fn typed_root(&self, name: &str, ty: Written) -> ReceiverChain {
        ReceiverChain {
            name: name.to_owned(),
            root: Root::Typed(ty),
            steps: Vec::new(),
            macros: self.macros.clone(),
        }
    }
}

impl Binder for Params {
    fn typed(&self, name: &str, ty: &syn::Type) -> Option<ReceiverChain> {
        self.body_type(ty).map(|ty| self.typed_root(name, ty))
    }

    fn bind_at(&mut self, name: String, origin: ReceiverChain, sites: BTreeSet<(usize, usize)>) {
        let binding = Binding {
            receiver: None,
            origin: Some(origin),
            after: None,
            sites: Some(sites),
        };
        self.bind(name, binding);
    }
}

impl Names for Params {
    fn named(&self, name: &str, at: (usize, usize)) -> Option<ReceiverChain> {
        if name == "self" {
            return self.this.clone();
        }
        let found = self.binding(name, at)?;
        // A local of a chain of `self` is still a name that a macro of the `fn` may bind.
        let mut origin = found.origin.clone()?;
        origin.macros.clone_from(&self.macros);
        Some(origin)
    }

    fn hides(&self, first: &str) -> bool {
        !self.proved || !self.macros.is_empty() || self.hide.contains(first)
    }

    fn self_type(&self) -> Option<Vec<String>> {
        self.self_type.clone()
    }

    fn macros(&self) -> Vec<String> {
        self.macros.clone()
    }
}

/// The kind and the path of a written parameter type: `T`, `&T` or `&mut T`, and one level only.
pub(in crate::scan) fn typed(ty: &Type) -> Option<(Vec<String>, SelfKind)> {
    match ty {
        Type::Reference(found) => {
            let kind = match found.mutability {
                Some(_) => SelfKind::Unique,
                None => SelfKind::Shared,
            };
            Some((plain_path(&found.elem)?, kind))
        }
        other => Some((plain_path(other)?, SelfKind::Value)),
    }
}

/// The parameters of a `fn` that have a proof: a plain identifier (`mut` is fine), bound once in
/// the signature and the body, with a written plain type that no generic parameter of the `fn` or
/// of the enclosing `impl` can hide. `scope` is the inline modules that enclose the `fn`; `this`
/// is the chain of `self` and the exact path of `Self` in a method of an exact block.
pub(super) fn read(
    (sig, block): (&Signature, &syn::Block),
    (outer, scope): (&[String], &[String]),
    inert: fn(&[Attribute]) -> bool,
    (this, self_type): (Option<ReceiverChain>, Option<Vec<String>>),
) -> Params {
    let mut bound = Bound {
        inert,
        gated: false,
        nested_macro: false,
        macros: BTreeSet::new(),
        counts: BTreeMap::new(),
        tainted: BTreeSet::new(),
    };
    bound.visit_signature(sig);
    bound.visit_block(block);
    if bound.gated || bound.nested_macro {
        return Params::bare(this);
    }
    let mut hidden: BTreeSet<String> = outer.iter().cloned().collect();
    hidden.extend(sig.generics.params.iter().filter_map(generic_name));
    let mut hide: BTreeSet<String> = hidden.clone();
    hide.extend(bound.counts.keys().cloned());
    hide.extend(bound.tainted.iter().cloned());
    let mut params = Params {
        found: BTreeMap::new(),
        proved: true,
        hide,
        macros: bound.macros.iter().cloned().collect(),
        this,
        self_type,
    };
    for input in &sig.inputs {
        let FnArg::Typed(param) = input else {
            continue;
        };
        let Pat::Ident(pattern) = &*param.pat else {
            let ty = with_self(written(&param.ty, &hidden), params.self_type.as_deref());
            let origin = params.typed_root("", ty);
            let place = (None, None);
            parts(&param.pat, &origin, (&bound, scope, place), &mut params);
            continue;
        };
        let name = plain(&pattern.ident);
        if !plain_ident(pattern) || !param.attrs.is_empty() || !once(&bound, &name) {
            continue;
        }
        let typed = typed(&param.ty)
            .filter(|(path, _)| !path.first().is_some_and(|first| hidden.contains(first)));
        // A signature names the items of the module: an item of the body hides none of it.
        let ty = with_self(written(&param.ty, &hidden), params.self_type.as_deref());
        let origin = Some(params.typed_root(&name, ty));
        let binding = Binding::new(&name, typed, origin, (scope, &bound), (None, None));
        params.bind(name, binding);
    }
    read_locals(block, &bound, (&hidden, scope), &mut params);
    Closures {
        bound: &bound,
        hidden: &hidden,
        scope,
        params: &mut params,
    }
    .visit_block(block);
    Bodies {
        binder: &mut params,
        tainted: &bound.tainted,
        counts: &bound.counts,
        depth: 0,
    }
    .visit_block(block);
    params
}

/// Bind each name of a pattern, bound once in the `fn`, to its part of the value `of` (AD-804).
fn parts(
    pattern: &Pat,
    of: &ReceiverChain,
    (bound, scope, place): (&Bound, &[String], Place),
    params: &mut Params,
) {
    if !params.proved {
        return;
    }
    for (name, steps) in destructure(pattern) {
        if !once(bound, &name) {
            continue;
        }
        let mut origin = of.clone();
        origin.name.clone_from(&name);
        origin.steps.extend(steps);
        origin.macros.clone_from(&params.macros);
        let binding = Binding::new(&name, None, Some(origin), (scope, bound), place.clone());
        params.bind(name, binding);
    }
}

fn plain_ident(ident: &syn::PatIdent) -> bool {
    ident.by_ref.is_none() && ident.subpat.is_none() && ident.attrs.is_empty()
}

fn once(bound: &Bound, name: &str) -> bool {
    bound.counts.get(name) == Some(&1) && !bound.tainted.contains(name)
}

/// Whether a plain written type of the body can be hidden by an item, a type parameter or a macro.
fn hides_plain(path: &[String], bound: &Bound, hidden: &BTreeSet<String>) -> bool {
    macro_hides_type(path, bound)
        || (path.first())
            .is_some_and(|name| hidden.contains(name) || bound.counts.contains_key(name))
}

/// Read only top-level initialized locals; their binding begins after the complete statement. A
/// typed local has its written type; an untyped one has the chain of its initializer (#1571).
fn read_locals(
    block: &syn::Block,
    bound: &Bound,
    (hidden, scope): (&BTreeSet<String>, &[String]),
    params: &mut Params,
) {
    for statement in &block.stmts {
        let syn::Stmt::Local(local) = statement else {
            continue;
        };
        let Some(init) = local.init.as_ref() else {
            continue;
        };
        let end = local.semi_token.spans[0].end();
        let place = (Some((end.line, end.column)), None);
        // A let-else and a tuple pattern bind the parts of the value (AD-804).
        let plain_let =
            matches!(&local.pat, Pat::Ident(_) | Pat::Type(_)) && init.diverge.is_none();
        if !plain_let {
            if let Some(of) = chain_of(&init.expr, params) {
                parts(&local.pat, &of, (bound, scope, place), params);
            }
            continue;
        }
        let (name, typed, origin) = match &local.pat {
            Pat::Type(pattern) => {
                let Pat::Ident(ident) = &*pattern.pat else {
                    continue;
                };
                let name = plain(&ident.ident);
                if !plain_ident(ident) || !pattern.attrs.is_empty() || !once(bound, &name) {
                    continue;
                }
                let typed =
                    typed(&pattern.ty).filter(|(path, _)| !hides_plain(path, bound, hidden));
                let origin = (params.body_type(&pattern.ty)).map(|ty| params.typed_root(&name, ty));
                (name, typed, origin)
            }
            Pat::Ident(ident) if plain_ident(ident) && once(bound, &plain(&ident.ident)) => {
                (plain(&ident.ident), None, chain_of(&init.expr, params))
            }
            _ => continue,
        };
        let binding = Binding::new(&name, typed, origin, (scope, bound), place);
        params.bind(name, binding);
    }
}

/// A macro can add a type or import in a function body without naming it at the call.
fn macro_hides_type(path: &[String], bound: &Bound) -> bool {
    !bound.macros.is_empty()
        && path
            .first()
            .is_some_and(|first| !matches!(first.as_str(), "crate" | "self" | "super"))
}

struct Closures<'a> {
    bound: &'a Bound,
    hidden: &'a BTreeSet<String>,
    scope: &'a [String],
    params: &'a mut Params,
}

impl<'ast> Visit<'ast> for Closures<'_> {
    fn visit_item(&mut self, _: &'ast Item) {}

    fn visit_expr_closure(&mut self, node: &'ast syn::ExprClosure) {
        let mut sites = ClosureSites::default();
        sites.visit_expr(&node.body);
        for input in &node.inputs {
            let Pat::Type(param) = input else { continue };
            let Pat::Ident(ident) = &*param.pat else {
                continue;
            };
            let name = plain(&ident.ident);
            if !plain_ident(ident) || !param.attrs.is_empty() || !once(self.bound, &name) {
                continue;
            }
            let typed =
                typed(&param.ty).filter(|(path, _)| !hides_plain(path, self.bound, self.hidden));
            let origin =
                (self.params.body_type(&param.ty)).map(|ty| self.params.typed_root(&name, ty));
            let Some(places) = sites.found.remove(&name) else {
                continue;
            };
            let place = (None, Some(places));
            let binding = Binding::new(&name, typed, origin, (self.scope, self.bound), place);
            self.params.bind(name, binding);
        }
        visit::visit_expr_closure(self, node);
    }
}

#[cfg(test)]
mod tests {
    use super::read;

    #[test]
    fn a_closure_binding_proves_only_receiver_sites_in_its_body() {
        let text = "fn f() { let _c = |s: &crate::c::S| s.m(); s.m(); }";
        let item: syn::ItemFn = syn::parse_str(text).unwrap();
        let found = read((&item.sig, &item.block), (&[], &[]), |_| true, (None, None));
        let first = text.find("s.m()").unwrap();
        let last = text.rfind("s.m()").unwrap();
        assert!(found.get("s", (1, first)).is_some());
        assert!(found.get("s", (1, last)).is_none());
    }
}
