// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The definitions that a decorator may replace (AD-782). They get no record, as before
//! (AD-518): a decorator can return any object. The writer notes each one, so `wrapped` can read
//! the form that a standard decorator gives. A definition of a module or a class whose members are
//! withheld, and a class that escapes, get no note: their names stay absent.

use std::collections::HashSet;

use ruff_python_ast::{Identifier, Stmt};

use super::found::Decorated;
use super::members;
use super::reader::Reader;
use crate::module::definition::Def;
use crate::module::Module;
use crate::survey::bound::Bound;

/// Note a definition of `holder` that a decorator may replace into `out`, unless its members are
/// withheld (`open`) or a class escapes. A method gets the names and the `__slots__` of its class
/// body.
pub(super) fn note<'m>(
    scan: &mut Reader<'m, '_>,
    (open, escaped): (bool, &HashSet<String>),
    (def, holder, class): (Def<'m>, &str, Option<(&Bound, &'m [Stmt])>),
    out: &mut Vec<Decorated<'m>>,
) {
    let name = match def {
        Def::Function(node) => Identifier::as_str(&node.name),
        Def::Class(node) => Identifier::as_str(&node.name),
    };
    if open || (class.is_none() && HashSet::contains(escaped, name)) {
        return;
    }
    let range = def.range(Module::text(scan.module));
    let evidence = Reader::evidence(scan, &range);
    let (class_names, slots) = match class {
        Some((bound, body)) => (Some(Bound::names(bound)), members::slots(body)),
        None => (None, Some(HashSet::new())),
    };
    out.push(Decorated {
        def,
        qualname: format!("{holder}.{name}"),
        class_names,
        slots,
        evidence,
    });
}
