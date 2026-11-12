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
//! A resolution must hold in every configuration. So `cfg` and `cfg_attr` are never inert: an
//! item, a block or a module under them is not exact, and neither is an `impl` block in a body.

use syn::{
    Attribute, GenericArgument, GenericParam, ItemImpl, PathArguments, ReceiverKind, Signature,
    Type,
};

use crate::definitions::{OnSelf, SelfKind};
use crate::tokens::plain;

/// The attributes that change no item and remove it in no configuration: an `impl` block or a
/// `fn` with only these is as written. Any other attribute can be a macro that rewrites the item,
/// or a `cfg` that removes it, so its `self` facts are not read.
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

/// Whether each attribute is inert or a tool attribute such as `rustfmt::skip`.
pub fn inert(attrs: &[Attribute]) -> bool {
    only(attrs, &[])
}

/// Whether a `mod` item, or the inner attributes of a file, keep the module in every configuration.
pub fn module_inert(attrs: &[Attribute]) -> bool {
    only(attrs, &MODULE)
}

/// Whether a struct or an enum keeps its type as written in every configuration.
pub fn type_inert(attrs: &[Attribute]) -> bool {
    only(attrs, &TYPE)
}

/// The kind of the `self` parameter as written, or `None` for a typed `self: X` or no `self`.
pub fn kind_of(sig: &Signature) -> Option<SelfKind> {
    match &sig.receiver()?.kind {
        ReceiverKind::Value => Some(SelfKind::Value),
        ReceiverKind::Reference(_, _, None) => Some(SelfKind::Shared),
        ReceiverKind::Reference(_, _, Some(_)) => Some(SelfKind::Unique),
        // A typed `self: X`, and any form that a later syn adds (`&pin self`): no kind.
        _ => None,
    }
}

/// Whether a generic argument binds a type or a const: a lifetime does not change which
/// inherent methods a type has.
fn binds_type(argument: &GenericArgument) -> bool {
    !matches!(argument, GenericArgument::Lifetime(_))
}

/// The path of the type of an `impl` block when the block is exact: a plain relative path with
/// no type or const argument, no type or const parameter on the block, and only inert attributes.
pub fn exact_path(item: &ItemImpl) -> Option<Vec<String>> {
    let generic =
        (item.generics.params.iter()).any(|param| !matches!(param, GenericParam::Lifetime(_)));
    if generic || !inert(&item.attrs) {
        return None;
    }
    let Type::Path(path) = &*item.self_ty else {
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

/// The last segment of a path `Self::m` in an expression.
pub fn self_member(node: &syn::ExprPath) -> Option<&syn::Ident> {
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
    /// An `impl` block: its exact type path and enclosing inline modules, or `None`.
    Impl(Option<(Vec<String>, Vec<String>)>),
    /// A method of an `impl` block: the `self` that its body sees, or `None`, and whether each
    /// attribute of the method is inert.
    Method(Option<OnSelf>, bool),
    /// A free `fn`, a `trait` or a `fn` of a `trait`.
    Opaque,
}

/// The stack of frames of the walk, and the depth of the inline modules that a `cfg` or another
/// attribute may remove.
#[derive(Debug, Default)]
pub struct Selves {
    frames: Vec<Frame>,
    gated: Vec<bool>,
}

impl Selves {
    /// Whether an enclosing inline module of the walk is not in every configuration.
    pub fn gated(&self) -> bool {
        self.gated.iter().any(|gated| *gated)
    }

    pub fn enter_module(&mut self, attrs: &[Attribute]) {
        self.gated.push(!module_inert(attrs));
    }

    pub fn leave_module(&mut self) {
        self.gated.pop();
    }

    /// Enter an `impl` block. A block in a body (`blocks > 0`) or in a gated module is not exact:
    /// a local item can hide the type name, and a gate can remove the block.
    pub fn enter_impl(&mut self, item: &ItemImpl, scope: &[String], blocks: usize) {
        let exact = exact_path(item)
            .filter(|_| blocks == 0 && !self.gated())
            .map(|path| (path, scope.to_vec()));
        self.frames.push(Frame::Impl(exact));
    }

    /// Enter a free `fn`, a `trait` or a `fn` of a `trait`: no `self` of an `impl` reaches in.
    pub fn enter_opaque(&mut self) {
        self.frames.push(Frame::Opaque);
    }

    /// Enter a `fn` of an `impl` block: it sees `self` when the block is exact, the `self`
    /// parameter has a kind, and each attribute of the `fn` is inert.
    pub fn enter_method(&mut self, sig: &Signature, attrs: &[Attribute]) {
        let block = match self.frames.last() {
            Some(Frame::Impl(Some(found))) => Some(found.clone()),
            _ => None,
        };
        let inert = inert(attrs);
        let on_self = block.filter(|_| inert).and_then(|(path, scope)| {
            let kind = Some(kind_of(sig)?);
            Some(OnSelf { path, scope, kind })
        });
        self.frames.push(Frame::Method(on_self, inert));
    }

    pub fn leave(&mut self) {
        self.frames.pop();
    }

    /// The `self` of a call whose receiver is `receiver`: only a plain `self` path has one.
    pub fn of(&self, receiver: &syn::Expr) -> Option<OnSelf> {
        let syn::Expr::Path(path) = receiver else {
            return None;
        };
        if path.qself.is_some() || !path.attrs.is_empty() || !path.path.is_ident("self") {
            return None;
        }
        let frame = (self.frames.iter().rev()).find(|f| !matches!(f, Frame::Impl(_)));
        match frame {
            Some(Frame::Method(on_self, _)) => on_self.clone(),
            _ => None,
        }
    }

    /// The type of `Self` for a path `Self::m`: the exact type of the nearest `impl` block, when
    /// no free `fn`, no `trait` and no method with an attribute that is not inert is between. A
    /// path has no `self` form.
    pub fn of_type(&self) -> Option<OnSelf> {
        let frame = (self.frames.iter().rev()).find(|f| !matches!(f, Frame::Method(_, true)));
        match frame {
            Some(Frame::Impl(Some((path, scope)))) => Some(OnSelf {
                path: path.clone(),
                scope: scope.clone(),
                kind: None,
            }),
            _ => None,
        }
    }
}
