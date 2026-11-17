// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The definitions that a decorator may replace (AD-782). They get no record, as before
//! (AD-518): a decorator can return any object. The writer notes each one, so `wrapped` can read
//! the form that a standard decorator gives. A definition of a module or a class whose members are
//! withheld, and a class that escapes, get no note: their names stay absent.

use std::collections::HashSet;

use ruff_python_ast::Stmt;

use super::found::Decorated;
use super::{members, Writer};
use crate::module::definition::Def;
use crate::survey::bound::Bound;

impl<'m> Writer<'m, '_> {
    /// Note a definition of `holder` that a decorator may replace. A method gets the names and the
    /// `__slots__` of its class body.
    pub(super) fn note_decorated(
        &mut self,
        def: Def<'m>,
        holder: &str,
        class: Option<(&Bound, &'m [Stmt])>,
    ) {
        let name = match def {
            Def::Function(node) => node.name.as_str(),
            Def::Class(node) => node.name.as_str(),
        };
        if self.open || (class.is_none() && HashSet::contains(&self.escaped, name)) {
            return;
        }
        let module = self.scan.module;
        let range = def.range(module.text());
        let evidence = self.scan.evidence(&range);
        let (class_names, slots) = match class {
            Some((bound, body)) => (Some(Bound::names(bound)), members::slots(body)),
            None => (None, Some(HashSet::new())),
        };
        self.decorated.push(Decorated {
            def,
            qualname: format!("{holder}.{name}"),
            class_names,
            slots,
            evidence,
        });
    }
}
