// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The definitions that a receiver chain names by a path (#1571, AD-804): the one free function of
//! a call `f(..)` or `m::f(..)`, and the one enum of a variant `T::V`. The file of the definition
//! must hold its name once.

use crate::definitions::{Definition, Form, Owner};
use crate::modules::{Frame, Index, Outcome};
use crate::routes::Route;
use crate::scan::{Reference, Via};

/// The one definition of `form` and `name` in the lexical module `lexical`, with the frame of its
/// file.
fn one<'f>(
    index: &'f Index<'_>,
    lexical: &str,
    (form, name): (Form, &str),
) -> Option<(&'f Frame<'f>, &'f Definition)> {
    let frame = index.frame(index.file_of(lexical)?)?;
    let scan = &frame.module.scan;
    let mut found = (scan.definitions.iter()).filter(|d| {
        d.form == form
            && (form != Form::Function || d.owner == Owner::Module)
            && d.name == name
            && frame.lexical_at(&d.scope) == lexical
    });
    let (definition, None) = (found.next()?, found.next()) else {
        return None;
    };
    (scan.counts.get(name) == Some(&1)).then_some((frame, definition))
}

/// The one free function that a path of a call names, in the file of the call or through a path.
pub(super) fn function<'f>(
    index: &'f Index<'_>,
    frame: &Frame<'_>,
    path: &[String],
    scope: &[String],
) -> Option<(&'f Frame<'f>, &'f Definition)> {
    let name = path.last()?;
    let local = path.len() == 1
        && frame.bound(name).is_empty()
        && frame.module.scan.counts.get(&**name) == Some(&1);
    let lexical = if local {
        frame.lexical_at(scope)
    } else {
        let reference = Reference {
            root: path.first()?.clone(),
            path: path.join("::"),
            names: path.to_vec(),
            scope: scope.to_vec(),
            via: Via::Path,
            ..Reference::default()
        };
        match index.resolve(frame, &reference) {
            Outcome::Edge(edge) if edge.symbol.as_ref() == Some(name) => edge.lexical,
            _ => return None,
        }
    };
    one(index, &lexical, (Form::Function, name))
}

/// A qualified call whose item route ends at a written free function, even under a new name.
pub(super) fn routed_function<'f>(
    index: &'f Index<'_>,
    frame: &Frame<'_>,
    path: &[String],
) -> Option<(&'f Frame<'f>, &'f Definition)> {
    if path.len() < 2 {
        return None;
    }
    let reference = Reference {
        names: path.to_vec(),
        ..Reference::default()
    };
    let route = Route::from_path(index, frame, &reference)?;
    if !route.complete || route.external_package.is_some() {
        return None;
    }
    let (lexical, name) = route.hops.last()?.rsplit_once('.')?;
    one(index, lexical, (Form::Function, name))
        .filter(|(frame, _)| !frame.module.gated && !frame.module.scan.module_macros)
}

/// With no explicit trait source, only zero-argument by-value prelude methods can win over
/// an inherent `&self` method. Use the union of the stable core/std preludes (Rust 1.97).
pub(super) fn shared_autoref(frame: &Frame<'_>, name: &str) -> bool {
    let scan = &frame.module.scan;
    frame.root() == frame.module.module
        && Vec::is_empty(&scan.concerns)
        && Vec::is_empty(&scan.macro_calls)
        && Vec::is_empty(&scan.extern_crates)
        && Vec::is_empty(&scan.orphans.block_items)
        && frame.leaves().next().is_none()
        && frame.globs().next().is_none()
        && !scan.definitions.iter().any(|d| d.form == Form::Trait)
        && !matches!(
            name,
            "into"
                | "try_into"
                | "into_future"
                | "into_iter"
                | "count"
                | "last"
                | "enumerate"
                | "peekable"
                | "flatten"
                | "fuse"
                | "collect"
                | "max"
                | "min"
                | "rev"
                | "unzip"
                | "copied"
                | "cloned"
                | "cycle"
                | "array_chunks"
                | "sum"
                | "product"
                | "is_sorted"
        )
}

/// The one enum `name` of `lexical`, when it has the variant `variant`.
pub(super) fn enum_with(index: &Index<'_>, (lexical, name): (&str, &str), variant: &str) -> bool {
    one(index, lexical, (Form::Enum, name))
        .is_some_and(|(_, def)| def.variants.iter().any(|v| v == variant))
}
