// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads of the items that a file defines (AD-351, slice 5b-4a): the free items of
//! a module, the members of an inherent `impl` and the members of a `trait`.
//!
//! The scan reads names and visibility as written. It does not read types, and it does not expand
//! macros: an item that a macro generates is no definition, and nothing is invented for it. An item
//! under a `cfg` is a definition, as in the module edges: the scan reads the union of the `cfg`
//! cases. A gap would make the whole scan incomplete, so the limit is in the member receipts of
//! each class (`symbols.rs`) and in AD-351.

use syn::{Ident, Item, ItemImpl, ItemTrait, Signature, Type};

use super::receivers::{exact_path, inert, item_name, kind_of, type_inert, written_type};
use super::state::Walker;
use crate::attrs::{impl_item_attributes, is_test_attributes};
use crate::definitions::{
    Access, BlockItem, Definition, Field, Form, Holder, ImplBlock, Member, Owner, TraitImpl,
};
use crate::tokens::plain;

fn access(vis: &syn::Visibility) -> Access {
    match vis {
        syn::Visibility::Public(_) => Access::Public,
        syn::Visibility::Inherited => Access::Private,
        syn::Visibility::Restricted(restricted) => {
            let path = restricted
                .path
                .segments
                .iter()
                .map(|segment| plain(&segment.ident))
                .collect::<Vec<_>>()
                .join("::");
            match (restricted.in_token.is_some(), path.as_str()) {
                (false, "self") | (true, "self") => Access::Private,
                (true, _) => Access::Package(format!("pub(in {path})")),
                (false, _) => Access::Package(format!("pub({path})")),
            }
        }
    }
}

/// The name of the type of an `impl` when it is one plain name.
fn type_name(item: &ItemImpl) -> Option<String> {
    let Type::Path(path) = &*item.self_ty else {
        return None;
    };
    let one = path.qself.is_none() && path.path.segments.len() == 1;
    let name = path.path.segments.first().map(|s| plain(&s.ident))?;
    (one && name != "Self").then_some(name)
}

/// Read the definition that `item` is. A block of a function holds no definition of the
/// module, so the walk reads nothing inside it.
pub(super) fn define_item(walker: &mut Walker<'_>, item: &Item) {
    if walker.blocks > 0 {
        return;
    }
    let (form, ident, vis): (Form, &Ident, &syn::Visibility) = match item {
        Item::Fn(f) => (Form::Function, &f.sig.ident, &f.vis),
        Item::Struct(s) => (Form::Struct, &s.ident, &s.vis),
        Item::Union(s) => (Form::Struct, &s.ident, &s.vis),
        Item::Enum(e) => (Form::Enum, &e.ident, &e.vis),
        Item::Trait(t) => (Form::Trait, &t.ident, &t.vis),
        Item::Const(c) => (Form::Constant, &c.ident, &c.vis),
        Item::Static(s) => (Form::Static, &s.ident, &s.vis),
        Item::Type(t) => (Form::Alias, &t.ident, &t.vis),
        Item::Macro(m) => return define_macro(walker, m),
        _ => return,
    };
    let mut found = definition(walker, form, ident, access(vis));
    match item {
        Item::Enum(e) => found.variants = e.variants.iter().map(|v| plain(&v.ident)).collect(),
        Item::Fn(f) => found.is_async = f.sig.asyncness.is_some(),
        _ => {}
    }
    walker.out.definitions.push(found);
}

pub(super) fn definition(
    walker: &Walker<'_>,
    form: Form,
    ident: &Ident,
    access: Access,
) -> Definition {
    Definition {
        form,
        name: plain(ident),
        scope: walker.inline.clone(),
        access,
        owner: Owner::Module,
        site: walker.site(ident.span()),
        variants: Vec::new(),
        receiver: false,
        is_async: false,
    }
}

/// `macro_rules!` is a definition. Any other macro call at item level defines nothing here.
pub(super) fn define_macro(walker: &mut Walker<'_>, item: &syn::ItemMacro) {
    let Some(name) = item.ident.as_ref() else {
        return;
    };
    let exported = item.attrs.iter().any(|a| a.path().is_ident("macro_export"));
    let access = if exported {
        Access::Public
    } else {
        Access::Package("macro_rules".to_owned())
    };
    let found = definition(walker, Form::Macro, name, access);
    walker.out.definitions.push(found);
}

/// Enter an `impl`. An inherent one defines members; `impl Trait for T` defines none.
pub(super) fn enter_impl(walker: &mut Walker<'_>, item: &ItemImpl) -> Holder {
    let holder = if item.trait_.is_some() {
        Holder::TraitImpl
    } else {
        Holder::Impl(type_name(item))
    };
    std::mem::replace(&mut walker.holder, holder)
}

/// Read an inherent `impl` block at any depth (#953): the path of its type and its members.
pub(super) fn impl_block(walker: &mut Walker<'_>, item: &ItemImpl) {
    if item.trait_.is_some() {
        return trait_impl(walker, item);
    }
    let path = match &*item.self_ty {
        Type::Path(path) if path.qself.is_none() && path.path.leading_colon.is_none() => {
            Some(path.path.segments.iter().map(|s| plain(&s.ident)).collect())
        }
        _ => None,
    };
    let tests = |member: &&syn::ImplItem| {
        walker.exclude_tests && is_test_attributes(impl_item_attributes(member))
    };
    let members = (item.items.iter().filter(|member| !tests(member)))
        .filter_map(|member| match member {
            syn::ImplItem::Fn(f) => Some(Member {
                name: plain(&f.sig.ident),
                access: access(&f.vis),
                receiver: f.sig.receiver().is_some(),
                kind: kind_of(&f.sig).filter(|_| inert(&f.attrs)),
                arity: (f.sig.inputs.len()).saturating_sub(usize::from(f.sig.receiver().is_some())),
                inert: inert(&f.attrs),
            }),
            syn::ImplItem::Const(c) => Some(Member {
                name: plain(&c.ident),
                access: access(&c.vis),
                receiver: false,
                kind: None,
                arity: 0,
                inert: inert(&c.attrs),
            }),
            _ => None,
        })
        .collect();
    let scope = walker.inline.clone();
    walker.out.impls.push(ImplBlock {
        path,
        scope,
        members,
        exact: exact_path(item).is_some() && walker.blocks == 0 && !walker.selves.gated(),
    });
}

/// Keep a struct or an enum at module level that every configuration has (AD-383).
pub(super) fn exact_type(walker: &mut Walker<'_>, item: &Item) {
    block_type(walker, item);
    let (ident, attrs) = match item {
        Item::Struct(found) => (&found.ident, &found.attrs),
        Item::Enum(found) => (&found.ident, &found.attrs),
        _ => return,
    };
    if walker.blocks == 0 && !walker.selves.gated() && type_inert(attrs) {
        walker.out.exact_types.insert(plain(ident));
        if let Item::Struct(found) = item {
            fields(walker, found);
        }
    }
}

fn fields(walker: &mut Walker<'_>, item: &syn::ItemStruct) {
    if item
        .generics
        .params
        .iter()
        .any(|p| !matches!(p, syn::GenericParam::Lifetime(_)))
    {
        return;
    }
    let syn::Fields::Named(fields) = &item.fields else {
        return;
    };
    if fields.named.iter().any(|field| !inert(&field.attrs)) {
        return;
    }
    for field in &fields.named {
        let (Some(name), Some((path, kind))) = (&field.ident, written_type(&field.ty)) else {
            continue;
        };
        let owner = plain(&item.ident);
        let name = plain(name);
        walker
            .out
            .fields
            .entry((owner, name))
            .or_default()
            .push(Field {
                scope: walker.inline.clone(),
                path,
                kind,
                access: access(&field.vis),
            });
    }
}

pub(super) fn enter_trait(walker: &mut Walker<'_>, item: &ItemTrait) -> Holder {
    let holder = Holder::Trait(plain(&item.ident), access(&item.vis));
    std::mem::replace(&mut walker.holder, holder)
}

pub(super) fn define_impl_item(walker: &mut Walker<'_>, item: &syn::ImplItem) {
    let Holder::Impl(ty) = walker.holder.clone() else {
        return;
    };
    if walker.blocks > 0 {
        return;
    }
    let owner = Owner::Impl(ty);
    match item {
        syn::ImplItem::Fn(f) => member(walker, &f.sig, (access(&f.vis), owner)),
        syn::ImplItem::Const(c) => {
            let mut found = definition(walker, Form::Constant, &c.ident, access(&c.vis));
            found.owner = owner;
            walker.out.definitions.push(found);
        }
        _ => {}
    }
}

pub(super) fn define_trait_item(walker: &mut Walker<'_>, item: &syn::TraitItem) {
    let Holder::Trait(name, access) = walker.holder.clone() else {
        return;
    };
    if walker.blocks > 0 {
        return;
    }
    let owner = Owner::Trait(name);
    match item {
        syn::TraitItem::Fn(f) => member(walker, &f.sig, (access, owner)),
        syn::TraitItem::Const(c) => {
            let mut found = definition(walker, Form::Constant, &c.ident, access);
            found.owner = owner;
            walker.out.definitions.push(found);
        }
        _ => {}
    }
}

/// A `fn` of an `impl` or a `trait`: static unless it has a `self` parameter.
pub(super) fn member(walker: &mut Walker<'_>, sig: &Signature, (access, owner): (Access, Owner)) {
    let mut found = definition(walker, Form::Function, &sig.ident, access);
    found.owner = owner;
    found.receiver = sig.receiver().is_some();
    found.is_async = sig.asyncness.is_some();
    walker.out.definitions.push(found);
}

/// The name of an item of an `extern` block.
pub(super) fn foreign_name(item: &syn::ForeignItem) -> Option<String> {
    let ident = match item {
        syn::ForeignItem::Fn(item) => &item.sig.ident,
        syn::ForeignItem::Static(item) => &item.ident,
        syn::ForeignItem::Type(item) => &item.ident,
        _ => return None,
    };
    Some(plain(ident))
}

// What the scan keeps for the pair gaps of trait impls in a third module (AD-516).

/// The path of the outermost nominal type of a self type, after `&`. A type parameter of the
/// block, a qualified path, an absolute path and any other type give `None`.
fn self_path(item: &ItemImpl) -> Option<Vec<String>> {
    let mut ty = &*item.self_ty;
    while let Type::Reference(inner) = ty {
        ty = &inner.elem;
    }
    let Type::Path(path) = ty else {
        return None;
    };
    let parameter = path.path.get_ident().is_some_and(|ident| {
        (item.generics.params.iter()).any(|param| match param {
            syn::GenericParam::Type(found) => found.ident == *ident,
            syn::GenericParam::Const(found) => found.ident == *ident,
            syn::GenericParam::Lifetime(_) => false,
        })
    });
    if path.qself.is_some() || path.path.leading_colon.is_some() || parameter {
        return None;
    }
    Some(path.path.segments.iter().map(|s| plain(&s.ident)).collect())
}

/// Keep an `impl Trait for T` at any depth.
fn trait_impl(walker: &mut Walker<'_>, item: &ItemImpl) {
    let trait_path = item.trait_.as_ref().map(|(path, _)| path);
    let found = TraitImpl {
        self_path: self_path(item),
        trait_path: trait_path
            .filter(|path| path.leading_colon.is_none())
            .map(|path| path.segments.iter().map(|s| plain(&s.ident)).collect()),
        scope: walker.inline.clone(),
        blocks: walker.block_ends.clone(),
        site: walker.site(item.impl_token.span),
    };
    walker.out.orphans.impls.push(found);
}

/// Keep each item that a block declares, and each `use` of a block.
fn block_type(walker: &mut Walker<'_>, item: &Item) {
    let Some(end) = walker.block_ends.last().copied() else {
        return;
    };
    let nominal = matches!(item, Item::Struct(_) | Item::Enum(_) | Item::Union(_));
    let name = match item {
        Item::Use(_) => None,
        other => match item_name(other) {
            Some(name) => Some(name),
            None => return,
        },
    };
    walker
        .out
        .orphans
        .block_items
        .push(BlockItem { name, end, nominal });
}
