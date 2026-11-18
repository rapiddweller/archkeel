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

use super::receivers::{
    exact_path, generic_names, inert, item_name, kind_of, returned, type_inert, written,
    written_type,
};
use super::state::Walker;
use crate::attrs::{impl_item_attributes, is_test_attributes};
use crate::definitions::{
    Access, BlockItem, Definition, Field, Form, Holder, ImplBlock, Member, Owner, SelfKind,
    TraitImpl, Written,
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
    if walker.blocks() > 0 {
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
        Item::ForeignMod(block) => return foreign_items(walker, block),
        // syn reads no item of this form (a nightly `pub macro`, a future item): it may
        // declare a public symbol that no record states (#1450).
        Item::Verbatim(tokens) => {
            let span = tokens
                .clone()
                .into_iter()
                .next()
                .map_or(proc_macro2::Span::call_site(), |t| t.span());
            let reason =
                "An item that the scan cannot parse may declare a public symbol".to_owned();
            return super::attributes::concern(walker, reason, span);
        }
        _ => return,
    };
    let mut found = definition(walker, form, ident, access(vis));
    match item {
        Item::Enum(e) => found.variants = e.variants.iter().map(|v| plain(&v.ident)).collect(),
        Item::Fn(f) => {
            found.is_async = f.sig.asyncness.is_some();
            // An attribute that is not inert can rewrite the signature (#1571).
            if inert(&f.attrs) {
                found.ret = returned(&f.sig, &std::collections::BTreeSet::new());
            }
        }
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
        ret: Written::Unknown,
    }
}

/// The functions and statics of an `extern` block are items of the module (#1450).
fn foreign_items(walker: &mut Walker<'_>, block: &syn::ItemForeignMod) {
    for item in &block.items {
        let (form, ident, vis) = match item {
            syn::ForeignItem::Fn(f) => (Form::Function, &f.sig.ident, &f.vis),
            syn::ForeignItem::Static(s) => (Form::Static, &s.ident, &s.vis),
            syn::ForeignItem::Type(t) => (Form::Alias, &t.ident, &t.vis),
            _ => continue,
        };
        let found = definition(walker, form, ident, access(vis));
        walker.out.definitions.push(found);
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
    let outer = generic_names(&item.generics);
    let members = (item.items.iter().filter(|member| !tests(member)))
        .filter_map(|member| match member {
            syn::ImplItem::Fn(f) => Some(Member {
                name: plain(&f.sig.ident),
                access: access(&f.vis),
                receiver: f.sig.receiver().is_some(),
                kind: kind_of(&f.sig).filter(|_| inert(&f.attrs)),
                arity: (f.sig.inputs.len()).saturating_sub(usize::from(f.sig.receiver().is_some())),
                inert: inert(&f.attrs),
                ret: returned(&f.sig, &outer),
            }),
            syn::ImplItem::Const(c) => Some(Member {
                name: plain(&c.ident),
                access: access(&c.vis),
                receiver: false,
                kind: None,
                arity: 0,
                inert: inert(&c.attrs),
                ret: Written::Unknown,
            }),
            _ => None,
        })
        .collect();
    let scope = walker.inline.clone();
    walker.out.impls.push(ImplBlock {
        path,
        scope,
        members,
        exact: exact_path(item).is_some() && walker.blocks() == 0 && !walker.selves.gated(),
    });
}

/// Keep a struct or an enum at module level that every configuration has (AD-383). A derive and
/// a helper attribute of a derive keep the type as written only when the derive is the macro of
/// the prelude (#1276): `use m::rewrite as derive;` makes `#[derive(..)]` an attribute macro that
/// can rewrite the type. Such a type waits for the proof of `collect.rs` (`helper_types`).
pub(super) fn exact_type(walker: &mut Walker<'_>, item: &Item) {
    block_type(walker, item);
    let (ident, attrs, is_type) = match item {
        Item::Struct(found) => (&found.ident, &found.attrs, true),
        Item::Enum(found) => (&found.ident, &found.attrs, true),
        Item::Trait(found) => (&found.ident, &found.attrs, false),
        _ => return,
    };
    if walker.blocks() != 0 || walker.selves.gated() {
        return;
    }
    let helper =
        |attr: &&syn::Attribute| attr.path().is_ident("serde") || attr.path().is_ident("schemars");
    let helpers: Vec<_> = attrs.iter().filter(helper).collect();
    let rest: Vec<_> = attrs.iter().filter(|a| !helper(a)).cloned().collect();
    if !type_inert(&rest) {
        return;
    }
    if helpers.is_empty() {
        let scope = walker.inline.clone();
        walker.out.exact_items.insert((scope, plain(ident)));
    }
    if !is_type {
        return;
    }
    let mut concerns = helper_concerns(walker, item, attrs, &helpers);
    if let Some(derive) = attrs.iter().find(|attr| attr.path().is_ident("derive")) {
        concerns.push(derive_concern(walker, derive));
    }
    if concerns.is_empty() {
        walker.out.exact_types.insert(plain(ident));
    } else {
        walker.out.helper_types.push((plain(ident), concerns));
    }
    // The fields count only for a type that is exact or that the proof makes exact.
    if let Item::Struct(found) = item {
        fields(walker, found);
    }
}

/// The proof that each helper attribute belongs to a derive of the type (#1250).
fn helper_concerns(
    walker: &Walker<'_>,
    item: &Item,
    attrs: &[syn::Attribute],
    helpers: &[&syn::Attribute],
) -> Vec<super::state::Concern> {
    if helpers.is_empty() {
        return Vec::new();
    }
    let tools = walker.tools && !crate::attrs::kinds::no_tools(attrs);
    let candidates = crate::attrs::model::Context::of(item, false, tools).candidates;
    helpers
        .iter()
        .map(|attr| {
            let mut concern = super::attributes::expansion_concern(
                walker,
                String::new(),
                attr.path().segments[0].ident.span(),
            );
            concern.proof = Some(crate::attrs::model::Proof::Helper {
                namespace: plain(&attr.path().segments[0].ident),
                candidates: candidates.clone(),
            });
            concern
        })
        .collect()
}

/// The proof that the name `derive` of an attribute is the macro of the prelude (#1276).
fn derive_concern(walker: &Walker<'_>, attr: &syn::Attribute) -> super::state::Concern {
    let span = attr.path().segments[0].ident.span();
    let mut concern = super::attributes::expansion_concern(walker, String::new(), span);
    concern.proof = Some(crate::attrs::model::Proof::Attribute(
        crate::attrs::model::Usage {
            path: vec!["derive".to_owned()],
            absolute: false,
            complete: true,
            block: false,
            prelude: walker.tools,
        },
    ));
    concern
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
    if item.fields.iter().any(|field| !inert(&field.attrs)) {
        return;
    }
    for (at, field) in item.fields.iter().enumerate() {
        // A field of another form keeps no plain path, only its written type (#1571).
        let (path, kind) = written_type(&field.ty).unwrap_or((Vec::new(), SelfKind::Value));
        let owner = plain(&item.ident);
        let name = field.ident.as_ref().map_or_else(|| at.to_string(), plain);
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
                written: written(&field.ty, &std::collections::BTreeSet::new()),
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
    if walker.blocks() > 0 {
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
    if walker.blocks() > 0 {
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
        runs: (item.items.iter()).any(|member| !matches!(member, syn::ImplItem::Type(_))),
        may_drop: may_define_destructor(item),
    };
    walker.out.orphans.impls.push(found);
}

fn may_define_destructor(item: &ItemImpl) -> bool {
    if !inert(&item.attrs) {
        return true;
    }
    let mut possible = false;
    for member in &item.items {
        if !inert(impl_item_attributes(member)) {
            possible = true;
            continue;
        }
        match member {
            syn::ImplItem::Fn(f) if plain(&f.sig.ident) == "drop" => possible = true,
            // A destructor has no other member. A macro cannot remove an inert sibling.
            syn::ImplItem::Fn(_) | syn::ImplItem::Type(_) | syn::ImplItem::Const(_) => {
                return false
            }
            _ => possible = true,
        }
    }
    possible
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
