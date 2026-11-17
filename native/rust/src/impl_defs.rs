// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The definitions that a receiver chain names by a path (#1571, AD-804): the one free function of
//! a call `f(..)` or `m::f(..)`, and the one enum of a variant `T::V`. The file of the definition
//! must hold its name once.

use crate::definitions::{Definition, Form, Owner};
use crate::modules::{Frame, Index, Outcome};
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

/// The one enum `name` of `lexical`, when it has the variant `variant`.
pub(super) fn enum_with(index: &Index<'_>, (lexical, name): (&str, &str), variant: &str) -> bool {
    one(index, lexical, (Form::Enum, name))
        .is_some_and(|(_, def)| def.variants.iter().any(|v| v == variant))
}
