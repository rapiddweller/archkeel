// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `self` of a method call (AD-383). The scan reads no types, but in a method of an `impl`
//! block the plain receiver `self` has the type of the block, and the `self` parameter as written
//! says whether it is the value, a shared or a unique reference. `impl_receivers.rs` resolves the
//! call from these facts. The walk keeps a stack of frames: each `impl` block, each method, and
//! each free `fn`, `trait` or `fn` of a `trait`. A free `fn` in a method body cannot use the `self`
//! of the method, and in a `trait` the type of `self` is generic: both frames give no `self`.
//!
//! A resolution must hold in every configuration. A `cfg` is not inert. A `cfg_attr` is inert only
//! when it can add lint attributes alone. An `impl` block in a body is not exact.

use syn::{
    punctuated::Punctuated, Attribute, GenericParam, ItemImpl, Meta, ReceiverKind, Signature,
};

use crate::definitions::{OnSelf, ReceiverChain, Root, SelfKind, Written};
use crate::tokens::{plain, LINTS};
use params::bound::Bound;
pub(in crate::scan) use params::item_name;
pub(in crate::scan) use params::typed as written_type;
use params::{plain_path, Params};
pub(in crate::scan) use written_types::{generic_names, returned, written};

/// The attributes besides the lints (`LINTS`) that change no item and remove it in no configuration:
/// an `impl` block or a `fn` with only these or a lint is as written. A conditional lint also
/// leaves the item as written. Any other attribute can be a macro that rewrites the item or a
/// `cfg` that removes it.
const INERT_BESIDES_LINTS: [&str; 7] = [
    "doc",
    "deprecated",
    "must_use",
    "inline",
    "cold",
    "track_caller",
    "automatically_derived",
];

/// The extra attributes that a `mod` item may have and stay in every configuration.
const MODULE: [&str; 2] = ["path", "macro_use"];

/// The extra attributes of a struct or an enum that keep its type as written. A derive only adds
/// items; a derived inherent member `m` beside a read one would be two members `m` (E0592).
const TYPE: [&str; 3] = ["derive", "repr", "non_exhaustive"];

fn only(attrs: &[Attribute], extra: &[&str]) -> bool {
    attrs.iter().all(|attr| {
        let path = attr.path();
        if path.is_ident("cfg_attr") {
            return conditional_lints(attr);
        }
        let tool = path.segments.len() == 2
            && path
                .segments
                .first()
                .is_some_and(|first| ["rustfmt", "clippy"].contains(&plain(&first.ident).as_str()));
        tool || path.get_ident().is_some_and(|name| {
            let name = plain(name);
            INERT_BESIDES_LINTS.contains(&name.as_str())
                || LINTS.contains(&name.as_str())
                || extra.contains(&name.as_str())
        })
    })
}

/// A conditional lint cannot remove or rewrite an item in any configuration.
fn conditional_lints(attr: &Attribute) -> bool {
    let Ok(args) = attr.parse_args_with(Punctuated::<Meta, syn::token::Comma>::parse_terminated)
    else {
        return false;
    };
    args.len() > 1
        && args.iter().skip(1).all(|item| {
            matches!(item, Meta::List(list) if list.path.get_ident().is_some_and(|id| LINTS.contains(&plain(id).as_str())))
        })
}

/// Whether each attribute is inert or a tool attribute such as `rustfmt::skip`.
pub(super) fn inert(attrs: &[Attribute]) -> bool {
    only(attrs, &[])
}

/// Whether a `mod` item, or the inner attributes of a file, keep the module in every configuration.
pub(super) fn module_inert(attrs: &[Attribute]) -> bool {
    only(attrs, &MODULE)
}

/// The exact `cfg` chain of a file module, or no proof for another module attribute.
pub(super) fn module_cfg(attrs: &[Attribute]) -> Option<Vec<String>> {
    let mut gates = Vec::new();
    for attr in attrs {
        if attr.path().is_ident("cfg") {
            let Meta::List(list) = &attr.meta else {
                return None;
            };
            if list.tokens.is_empty() {
                return None;
            }
            gates.push(list.tokens.to_string());
        } else if attr.path().is_ident("cfg_attr") || !inert(std::slice::from_ref(attr)) {
            return None;
        }
    }
    Some(gates)
}

/// Whether a struct or an enum keeps its type as written in every configuration.
pub(super) fn type_inert(attrs: &[Attribute]) -> bool {
    only(attrs, &TYPE)
}

/// The kind of the `self` parameter as written, or `None` for a typed `self: X` or no `self`.
pub(super) fn kind_of(sig: &Signature) -> Option<SelfKind> {
    match &sig.receiver()?.kind {
        ReceiverKind::Value => Some(SelfKind::Value),
        ReceiverKind::Reference(_, _, None) => Some(SelfKind::Shared),
        ReceiverKind::Reference(_, _, Some(_)) => Some(SelfKind::Unique),
        // A typed `self: X`, and any form that a later syn adds (`&pin self`): no kind.
        _ => None,
    }
}

/// The path of the type of an `impl` block when the block is exact: a plain relative path with
/// no type or const argument, no type or const parameter on the block, and only inert attributes.
pub(super) fn exact_path(item: &ItemImpl) -> Option<Vec<String>> {
    let generic =
        (item.generics.params.iter()).any(|param| !matches!(param, GenericParam::Lifetime(_)));
    if generic || !inert(&item.attrs) {
        return None;
    }
    plain_path(&item.self_ty)
}

/// The last segment of a path `Self::m` in an expression.
pub(super) fn self_member(node: &syn::ExprPath) -> Option<&syn::Ident> {
    let segments = &node.path.segments;
    let first = segments.first().filter(|first| first.ident == "Self")?;
    let last = segments
        .last()
        .filter(|_| segments.len() == 2 && node.qself.is_none())?;
    (first.arguments.is_none()).then_some(&last.ident)
}

/// The base and at most two named fields of a receiver.
fn field_chain(receiver: &syn::Expr) -> Option<(&syn::Expr, Vec<String>)> {
    let mut current = receiver;
    let mut fields = Vec::new();
    while let syn::Expr::Field(field) = current {
        let syn::Member::Named(name) = &field.member else {
            return None;
        };
        if !field.attrs.is_empty() || fields.len() == 2 {
            return None;
        }
        fields.push(plain(name));
        current = &field.base;
    }
    fields.reverse();
    Some((current, fields))
}

/// The chain of a plain `self` of a method of an exact block: the type of the block behind the
/// reference of the `self` parameter. No name and no macro can bind `self` again.
fn this_chain(on_self: &OnSelf) -> Option<ReceiverChain> {
    let ty = Written::Path(on_self.path.clone(), Vec::new());
    let ty = match on_self.kind? {
        SelfKind::Value => ty,
        kind => Written::Ref(kind, Box::new(ty)),
    };
    Some(ReceiverChain {
        name: "self".to_owned(),
        root: Root::Typed(ty),
        steps: Vec::new(),
        macros: Vec::new(),
    })
}

/// A frame of the walk that decides what a plain `self` and `Self` are.
#[derive(Debug)]
enum Frame {
    /// An `impl` block: its exact type path and enclosing inline modules, or `None`, the names
    /// of its type and const parameters, and whether each attribute of the block is inert.
    Impl(Option<(Vec<String>, Vec<String>)>, Vec<String>, bool),
    /// A method of an `impl` block: the `self` that its body sees, or `None`, whether each
    /// attribute of the method is inert, and its typed parameters.
    Method(Option<OnSelf>, bool, Params),
    /// A free `fn` with its typed parameters, a `trait` or a `fn` of a `trait` (no parameters).
    Opaque(Params),
}

/// The typed parameters of a `fn` (AD-524).
#[path = "scan_params.rs"]
mod params;

/// The types as written (#1571, AD-804).
#[path = "scan_written.rs"]
mod written_types;

/// The receiver of a method call as a chain (#1571, AD-804).
#[path = "scan_chains.rs"]
mod chains;

/// The receiver sites of a closure or a loop body (AD-524, #1571).
#[path = "scan_sites.rs"]
mod sites;

/// The names that a pattern of a body binds (#1571, AD-804).
#[path = "scan_bodies.rs"]
mod bodies;

fn read_bindings(
    (sig, block): (&Signature, &syn::Block),
    scope: (&[String], &[String]),
    (this, self_type): (Option<ReceiverChain>, Option<Vec<String>>),
) -> Params {
    let Some(bound) = Bound::read(sig, block, inert) else {
        return Params::bare(this);
    };
    let mut params = params::read((sig, block), scope, &bound, (this, self_type));
    bodies::extend(block, &mut params, &bound);
    params
}

/// The stack of frames of the walk, and the depth of the inline modules that a `cfg` or another
/// attribute may remove.
#[derive(Debug, Default)]
pub(super) struct Selves {
    frames: Vec<Frame>,
    gated: Vec<bool>,
}

impl Selves {
    /// Whether an enclosing inline module of the walk is not in every configuration.
    pub(super) fn gated(&self) -> bool {
        self.gated.iter().any(|gated| *gated)
    }

    pub(super) fn enter_module(&mut self, attrs: &[Attribute]) {
        self.gated.push(!module_inert(attrs));
    }

    pub(super) fn leave_module(&mut self) {
        self.gated.pop();
    }

    /// Enter an `impl` block. A block in a body (`blocks > 0`) or in a gated module is not exact:
    /// a local item can hide the type name, and a gate can remove the block.
    pub(super) fn enter_impl(&mut self, item: &ItemImpl, scope: &[String], blocks: usize) {
        let exact = exact_path(item)
            .filter(|_| blocks == 0 && !self.gated())
            .map(|path| (path, scope.to_vec()));
        let names = (item.generics.params.iter()).filter_map(params::generic_name);
        self.frames
            .push(Frame::Impl(exact, names.collect(), inert(&item.attrs)));
    }

    /// Enter a `trait` or a `fn` of a `trait`: no `self` of an `impl` reaches in, and no
    /// parameter has a proof.
    pub(super) fn enter_opaque(&mut self) {
        self.frames.push(Frame::Opaque(Params::default()));
    }

    /// Enter a free `fn`: no `self` of an `impl` reaches in, and its typed parameters have a
    /// proof when the `fn` is in no gated module and no block, and has only inert attributes: a
    /// block can declare an item that hides the type that the signature names.
    pub(super) fn enter_function(&mut self, item: &syn::ItemFn, at: (&[String], usize)) {
        let (scope, blocks) = at;
        let proved = inert(&item.attrs) && !self.gated() && blocks == 0;
        let found = proved.then(|| {
            let bodies = (&item.sig, &*item.block);
            read_bindings(bodies, (&[], scope), (None, None))
        });
        self.frames.push(Frame::Opaque(found.unwrap_or_default()));
    }

    /// Enter a `fn` of an `impl` block: it sees `self` when the block is exact, the `self`
    /// parameter has a kind, and each attribute of the `fn` is inert. Its typed parameters have a
    /// proof when the `fn` has only inert attributes and the module is not gated.
    pub(super) fn enter_method(&mut self, item: &syn::ImplItemFn, at: (&[String], usize)) {
        let (scope, blocks) = at;
        let (sig, attrs) = (&item.sig, &item.attrs);
        let (block, outer, block_inert) = match self.frames.last() {
            Some(Frame::Impl(found, names, kept)) => (found.clone(), names.clone(), *kept),
            _ => (None, Vec::new(), false),
        };
        let kept = inert(attrs);
        let proved = kept && block_inert && !self.gated() && blocks == 0;
        let self_type = block.clone().filter(|_| kept).map(|(path, _)| path);
        let on_self = block.filter(|_| kept).and_then(|(path, scope)| {
            let kind = Some(kind_of(sig)?);
            Some(OnSelf {
                name: "self".to_owned(),
                path,
                scope,
                kind,
                macros: Vec::new(),
                fields: Vec::new(),
            })
        });
        let this = on_self.as_ref().and_then(this_chain);
        let found = match proved {
            true => read_bindings((sig, &item.block), (&outer, scope), (this, self_type)),
            false => Params::bare(this),
        };
        self.frames.push(Frame::Method(on_self, kept, found));
    }

    pub(super) fn leave(&mut self) {
        self.frames.pop();
    }

    /// The proof of a call whose receiver is `receiver`: a plain `self` path has the type of its
    /// block, and a plain parameter name has its written type (AD-524).
    pub(super) fn of(&self, receiver: &syn::Expr) -> Option<OnSelf> {
        if matches!(receiver, syn::Expr::Field(_)) {
            let (current, fields) = field_chain(receiver)?;
            let mut base = self.of(current)?;
            base.fields = fields;
            return Some(base);
        }
        let syn::Expr::Path(path) = receiver else {
            return None;
        };
        if path.qself.is_some() || !path.attrs.is_empty() {
            return None;
        }
        let name = path.path.get_ident()?;
        let frame = (self.frames.iter().rev()).find(|f| !matches!(f, Frame::Impl(..)));
        match frame {
            Some(Frame::Method(on_self, _, _)) if name == "self" => on_self.clone(),
            Some(Frame::Method(_, _, found) | Frame::Opaque(found)) if name != "self" => {
                let at = name.span().start();
                found
                    .get(&plain(name), (at.line, at.column))
                    .filter(|_| !self.gated())
                    .cloned()
            }
            _ => None,
        }
    }

    /// The receiver chain of a method call (#1571), or `None`: in a gated module, a `trait` or
    /// outside a `fn`.
    pub(super) fn chain(&self, receiver: &syn::Expr) -> Option<ReceiverChain> {
        let frame = (self.frames.iter().rev()).find(|f| !matches!(f, Frame::Impl(..)));
        match frame {
            Some(Frame::Method(_, _, found) | Frame::Opaque(found)) if !self.gated() => {
                chains::chain_of(receiver, found)
            }
            _ => None,
        }
    }

    /// The type of `Self` for a path `Self::m`: the exact type of the nearest `impl` block, when
    /// no free `fn`, no `trait` and no method with an attribute that is not inert is between. A
    /// path has no `self` form.
    pub(super) fn of_type(&self) -> Option<OnSelf> {
        let frame = (self.frames.iter().rev()).find(|f| !matches!(f, Frame::Method(_, true, _)));
        match frame {
            Some(Frame::Impl(Some((path, scope)), _, _)) => Some(OnSelf {
                name: "Self".to_owned(),
                path: path.clone(),
                scope: scope.clone(),
                kind: None,
                macros: Vec::new(),
                fields: Vec::new(),
            }),
            _ => None,
        }
    }
}
