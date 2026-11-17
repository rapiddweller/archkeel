// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The receiver of a method call as a chain (#1571, AD-804): a root and the steps after it. The
//! root is a name that the `fn` binds with a proof (`self`, a typed parameter, a local), a
//! literal, a call of a path, a struct literal or a path to a variant. The steps are named fields,
//! method calls and `?`. The scan reads no types: `impl_types.rs` resolves the chain against the
//! written types of the workspace. Any other expression gives no chain, and the call keeps its
//! gaps.

use syn::{Expr, Lit, Member, PathArguments};

use crate::definitions::{ReceiverChain, Root, SelfKind, Step};
use crate::tokens::plain;

/// The longest chain that the scan reads.
const MAX_STEPS: usize = 8;

/// What the `fn` around an expression binds.
pub(super) trait Names {
    /// The chain of a name at a place: `self`, or a parameter or local with a proof.
    fn named(&self, name: &str, at: (usize, usize)) -> Option<ReceiverChain>;
    /// Whether a path that the body writes may name an item of the body: the `fn` binds its first
    /// segment, or a macro call of the `fn` can add an item.
    fn hides(&self, first: &str) -> bool;
    /// The exact type path of `Self`, for `Self::f(..)` and `Self { .. }`.
    fn self_type(&self) -> Option<Vec<String>>;
    /// The macros of the `fn` that are no silent macro of `std` (AD-524).
    fn macros(&self) -> Vec<String>;
}

/// The chain of a receiver, or `None` when the scan cannot read it.
pub(super) fn chain_of(expr: &Expr, names: &dyn Names) -> Option<ReceiverChain> {
    let mut steps = Vec::new();
    let mut current = expr;
    loop {
        if steps.len() > MAX_STEPS {
            return None;
        }
        match current {
            Expr::Field(found) if found.attrs.is_empty() => {
                let Member::Named(name) = &found.member else {
                    return None;
                };
                steps.push(Step::Field(plain(name)));
                current = &found.base;
            }
            Expr::MethodCall(found) if found.attrs.is_empty() => {
                steps.push(Step::Call(plain(&found.method), found.args.len()));
                current = &found.receiver;
            }
            Expr::Try(found) if found.attrs.is_empty() => {
                steps.push(Step::Try);
                current = &found.expr;
            }
            Expr::Reference(found) if found.attrs.is_empty() => {
                let kind = match found.mutability {
                    Some(_) => SelfKind::Unique,
                    None => SelfKind::Shared,
                };
                steps.push(Step::Borrow(kind));
                current = &found.expr;
            }
            Expr::Paren(found) if found.attrs.is_empty() => current = &found.expr,
            Expr::Group(found) if found.attrs.is_empty() => current = &found.expr,
            _ => break,
        }
    }
    steps.reverse();
    let mut chain = root_of(current, names)?;
    chain.steps.extend(steps);
    (chain.steps.len() <= MAX_STEPS).then_some(chain)
}

/// The segments of a value path with no qualified self and no generic arguments. A first
/// segment `Self` becomes the exact type of the block.
fn value_path(path: &syn::ExprPath, names: &dyn Names) -> Option<Vec<String>> {
    let plain_path = path.qself.is_none()
        && path.attrs.is_empty()
        && path.path.leading_colon.is_none()
        && (path.path.segments.iter()).all(|s| matches!(s.arguments, PathArguments::None));
    if !plain_path {
        return None;
    }
    path_of(&path.path, names)
}

fn path_of(path: &syn::Path, names: &dyn Names) -> Option<Vec<String>> {
    let mut segments: Vec<String> = path.segments.iter().map(|s| plain(&s.ident)).collect();
    if segments.first().is_some_and(|first| first == "Self") {
        let mut found = names.self_type()?;
        found.extend(segments.drain(1..));
        segments = found;
    } else if names.hides(segments.first()?) {
        return None;
    }
    Some(segments)
}

fn chain(name: String, root: Root, names: &dyn Names) -> Option<ReceiverChain> {
    Some(ReceiverChain {
        name,
        root,
        steps: Vec::new(),
        macros: names.macros(),
    })
}

/// The root of a chain.
fn root_of(expr: &Expr, names: &dyn Names) -> Option<ReceiverChain> {
    match expr {
        Expr::Path(found) if found.path.segments.len() == 1 => {
            let ident = found.path.get_ident()?;
            let plain_name = found.qself.is_none() && found.attrs.is_empty();
            let at = ident.span().start();
            plain_name
                .then(|| names.named(&plain(ident), (at.line, at.column)))
                .flatten()
        }
        Expr::Path(found) => {
            let path = value_path(found, names)?;
            chain(path.join("::"), Root::Value(path), names)
        }
        Expr::Call(found) if found.attrs.is_empty() => {
            let Expr::Path(func) = &*found.func else {
                return None;
            };
            let path = value_path(func, names)?;
            chain(path.join("::"), Root::Call(path, found.args.len()), names)
        }
        Expr::Struct(found) if found.attrs.is_empty() && found.qself.is_none() => {
            let arguments = found.path.segments.iter();
            if found.path.leading_colon.is_some()
                || arguments
                    .clone()
                    .any(|s| !matches!(s.arguments, PathArguments::None))
            {
                return None;
            }
            let path = path_of(&found.path, names)?;
            chain(path.join("::"), Root::Value(path), names)
        }
        Expr::Lit(found) if found.attrs.is_empty() => {
            let kind = match &found.lit {
                Lit::Str(_) => "str",
                Lit::Char(_) => "char",
                Lit::Bool(_) => "bool",
                Lit::Int(_) => "int",
                Lit::Float(_) => "float",
                _ => return None,
            };
            // No name of the `fn` takes part: no macro can bind a literal again.
            let mut found = chain(kind.to_owned(), Root::Literal(kind), names)?;
            found.macros.clear();
            Some(found)
        }
        _ => None,
    }
}

#[cfg(test)]
#[path = "scan_chains_tests.rs"]
mod tests;
