// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed parameters of a `fn` (AD-518). A parameter `x: T`, `x: &T` or `x: &mut T` with a
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

use std::collections::{BTreeMap, BTreeSet};

use proc_macro2::{TokenStream, TokenTree};
use syn::visit::{self, Visit};
use syn::{FnArg, GenericParam, Pat, Signature, Type};

use super::plain_path;
use crate::definitions::{OnSelf, SelfKind};
use crate::tokens::{plain, NO_BIND_MACROS};

/// The name of a type or const parameter. A lifetime has none.
pub(super) fn generic_name(param: &GenericParam) -> Option<String> {
    match param {
        GenericParam::Type(found) => Some(plain(&found.ident)),
        GenericParam::Const(found) => Some(plain(&found.ident)),
        GenericParam::Lifetime(_) => None,
    }
}

/// The parameters of one `fn` that have a proof, by name.
#[derive(Debug, Default)]
pub(super) struct Params(BTreeMap<String, OnSelf>);

impl Params {
    pub(super) fn get(&self, name: &str) -> Option<&OnSelf> {
        self.0.get(name)
    }
}

/// How the body and the signature bind names.
#[derive(Default)]
struct Bound {
    /// How many times each name is bound by a pattern or an item.
    counts: BTreeMap<String, usize>,
    /// Names that a `use` or a macro call may bind.
    tainted: BTreeSet<String>,
}

impl Bound {
    fn count(&mut self, name: String) {
        *self.counts.entry(name).or_default() += 1;
    }

    fn taint(&mut self, tokens: TokenStream) {
        for tree in tokens {
            match tree {
                TokenTree::Ident(ident) => {
                    self.tainted.insert(plain(&ident));
                }
                TokenTree::Group(group) => self.taint(group.stream()),
                _ => {}
            }
        }
    }

    fn leaves(&mut self, tree: &syn::UseTree) {
        match tree {
            syn::UseTree::Path(path) => self.leaves(&path.tree),
            syn::UseTree::Group(group) => group.items.iter().for_each(|item| self.leaves(item)),
            syn::UseTree::Name(name) => self.count(plain(&name.ident)),
            syn::UseTree::Rename(rename) => self.count(plain(&rename.rename)),
            // A glob never shadows a local, and an item of a block wins over it.
            syn::UseTree::Glob(_) => {}
        }
    }
}

impl<'ast> Visit<'ast> for Bound {
    fn visit_pat_ident(&mut self, node: &'ast syn::PatIdent) {
        self.count(plain(&node.ident));
        visit::visit_pat_ident(self, node);
    }

    fn visit_item(&mut self, node: &'ast syn::Item) {
        match node {
            syn::Item::Use(found) => self.leaves(&found.tree),
            other => {
                if let Some(name) = declared(other) {
                    self.count(name);
                }
            }
        }
        visit::visit_item(self, node);
    }

    fn visit_macro(&mut self, node: &'ast syn::Macro) {
        let silent = node
            .path
            .get_ident()
            .is_some_and(|name| NO_BIND_MACROS.contains(&plain(name).as_str()));
        if !silent {
            self.taint(node.tokens.clone());
        }
        visit::visit_macro(self, node);
    }
}

/// The name that an item declares in the value namespace or any other.
fn declared(item: &syn::Item) -> Option<String> {
    let ident = match item {
        syn::Item::Fn(found) => &found.sig.ident,
        syn::Item::Struct(found) => &found.ident,
        syn::Item::Enum(found) => &found.ident,
        syn::Item::Union(found) => &found.ident,
        syn::Item::Trait(found) => &found.ident,
        syn::Item::Type(found) => &found.ident,
        syn::Item::Const(found) => &found.ident,
        syn::Item::Static(found) => &found.ident,
        syn::Item::Mod(found) => &found.ident,
        syn::Item::Macro(found) => found.ident.as_ref()?,
        syn::Item::ExternCrate(found) => found.rename.as_ref().map_or(&found.ident, |r| &r.1),
        _ => return None,
    };
    Some(plain(ident))
}

/// The kind and the path of a written parameter type: `T`, `&T` or `&mut T`, and one level only.
fn typed(ty: &Type) -> Option<(Vec<String>, SelfKind)> {
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
/// of the enclosing `impl` can hide. `scope` is the inline modules that enclose the `fn`.
pub(super) fn read(
    sig: &Signature,
    block: &syn::Block,
    outer: &[String],
    scope: &[String],
) -> Params {
    let mut bound = Bound::default();
    bound.visit_signature(sig);
    bound.visit_block(block);
    let mut hidden: BTreeSet<String> = outer.iter().cloned().collect();
    hidden.extend(sig.generics.params.iter().filter_map(generic_name));
    let mut found = BTreeMap::new();
    for input in &sig.inputs {
        let FnArg::Typed(param) = input else {
            continue;
        };
        let Pat::Ident(pattern) = &*param.pat else {
            continue;
        };
        let plain_pattern = pattern.by_ref.is_none()
            && pattern.subpat.is_none()
            && pattern.attrs.is_empty()
            && param.attrs.is_empty();
        let name = plain(&pattern.ident);
        let once = bound.counts.get(&name) == Some(&1) && !bound.tainted.contains(&name);
        let Some((path, kind)) = typed(&param.ty) else {
            continue;
        };
        let generic = path.first().is_some_and(|first| hidden.contains(first));
        if plain_pattern && once && !generic {
            let on_self = OnSelf {
                name: name.clone(),
                path,
                scope: scope.to_vec(),
                kind: Some(kind),
            };
            found.insert(name, on_self);
        }
    }
    Params(found)
}
