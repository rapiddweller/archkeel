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
    punctuated::Punctuated, Attribute, GenericParam, ItemImpl, Meta, ReceiverKind, Signature, Token,
};

use crate::definitions::{OnSelf, SelfKind};
use crate::tokens::{plain, LINTS};
pub(in crate::scan) use params::item_name;
use params::{plain_path, Params};

/// The attributes that change no item and remove it in no configuration: an `impl` block or a
/// `fn` with only these is as written. A conditional lint also leaves the item as written.
/// Any other attribute can be a macro that rewrites the item or a `cfg` that removes it.
const INERT: [&str; 12] = [
    "allow",
    "warn",
    "deny",
    "forbid",
    "expect",
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
            INERT.contains(&name.as_str()) || extra.contains(&name.as_str())
        })
    })
}

/// A conditional lint cannot remove or rewrite an item in any configuration.
fn conditional_lints(attr: &Attribute) -> bool {
    let Ok(args) = attr.parse_args_with(Punctuated::<Meta, Token![,]>::parse_terminated) else {
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
        let found = proved.then(|| params::read(&item.sig, &item.block, &[], scope, inert));
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
        let found = proved.then(|| params::read(sig, &item.block, &outer, scope, inert));
        let on_self = block.filter(|_| kept).and_then(|(path, scope)| {
            let kind = Some(kind_of(sig)?);
            Some(OnSelf {
                name: "self".to_owned(),
                path,
                scope,
                kind,
                macros: Vec::new(),
            })
        });
        self.frames
            .push(Frame::Method(on_self, kept, found.unwrap_or_default()));
    }

    pub(super) fn leave(&mut self) {
        self.frames.pop();
    }

    /// The proof of a call whose receiver is `receiver`: a plain `self` path has the type of its
    /// block, and a plain parameter name has its written type (AD-524).
    pub(super) fn of(&self, receiver: &syn::Expr) -> Option<OnSelf> {
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
                found.get(&plain(name)).filter(|_| !self.gated()).cloned()
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
            }),
            _ => None,
        }
    }
}
