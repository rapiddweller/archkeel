// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The kind of a class that Python binds when the class statement runs (AD-514, rule 6).
//!
//! A class has a kind only when each base is proven: a builtin that no statement of the module
//! rebinds, a name of `typing` or `enum` that its one plain import binds, or a class of the same
//! module that has a record. A keyword (`metaclass=`), a type parameter list or any other base
//! can change what the statement gives, so the class has no kind and no record.

use std::collections::HashMap;

use ruff_python_ast::{Expr, Stmt, StmtClassDef};
use ruff_text_size::Ranged;

use crate::survey::binders::Binders;
use crate::survey::bound::Bound;

/// The kind of a class with a record.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Kind {
    Plain,
    Protocol,
    Enum,
}

/// The builtin classes that give a class no other kind and no namespace.
const BUILTIN_BASES: [&str; 12] = [
    "object",
    "Exception",
    "BaseException",
    "ValueError",
    "TypeError",
    "RuntimeError",
    "KeyError",
    "dict",
    "list",
    "tuple",
    "str",
    "int",
];

/// The classes of `enum` whose subclass is an enum.
const ENUM_BASES: [&str; 5] = ["Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"];

/// What a class statement reads to know its bases.
pub(super) struct Reading<'a> {
    pub body: &'a [Stmt],
    pub bound: &'a Bound,
    pub binders: &'a Binders,
    /// The class body that holds this class, for a nested class: it can bind a name of a base.
    pub enclosing: Option<&'a Bound>,
    /// The classes of the module body that have a record, by name (a top-level class only).
    pub local: &'a HashMap<String, Kind>,
}

impl<'a> Reading<'a> {
    /// The reading of a class of the module body.
    pub(super) fn top(
        body: &'a [Stmt],
        bound: &'a Bound,
        binders: &'a Binders,
        local: &'a HashMap<String, Kind>,
    ) -> Self {
        Reading {
            body,
            bound,
            binders,
            enclosing: None,
            local,
        }
    }

    /// The reading of a class nested in the class body with the binders `held`.
    pub(super) fn within(self, held: &'a Bound) -> Self {
        Reading {
            enclosing: Some(held),
            ..self
        }
    }
}

/// What one base is.
enum Base {
    Plain,
    Protocol,
    Enum,
}

/// The kind of `node`, or `None` when a base or a keyword leaves it open.
pub(super) fn of(node: &StmtClassDef, reading: &Reading<'_>) -> Option<Kind> {
    if node.type_params.is_some() {
        return None;
    }
    let arguments = node.arguments.as_deref();
    if arguments.is_some_and(|arguments| !arguments.keywords.is_empty()) {
        return None;
    }
    let (mut protocol, mut enumeration) = (false, false);
    for base in arguments.map_or(&[][..], |arguments| &arguments.args) {
        match classify(base, reading)? {
            Base::Plain => {}
            Base::Protocol => protocol = true,
            Base::Enum => enumeration = true,
        }
    }
    match (protocol, enumeration) {
        (true, true) => None,
        (true, false) => Some(Kind::Protocol),
        (false, true) => Some(Kind::Enum),
        (false, false) => Some(Kind::Plain),
    }
}

fn classify(base: &Expr, reading: &Reading<'_>) -> Option<Base> {
    if let Expr::Name(name) = base {
        let name = name.id.as_str();
        if reading
            .enclosing
            .is_some_and(|held| held.names().contains(name))
        {
            return None;
        }
        if let Some(kind) = reading
            .local
            .get(name)
            .filter(|_| reading.enclosing.is_none())
        {
            // A class that derives from a protocol class is no protocol itself.
            return Some(match kind {
                Kind::Enum => Base::Enum,
                Kind::Plain | Kind::Protocol => Base::Plain,
            });
        }
        if BUILTIN_BASES.contains(&name) && reading.binders.builtin_visible(name) {
            return Some(Base::Plain);
        }
    }
    let (module, symbol) = imported(base, reading)?;
    match (module.as_str(), symbol.as_str()) {
        ("typing" | "typing_extensions", "Protocol") => Some(Base::Protocol),
        ("enum", symbol) if ENUM_BASES.contains(&symbol) => Some(Base::Enum),
        _ => None,
    }
}

/// The module and the name that an expression reads through the one plain import of its root:
/// `from enum import Enum` (`Enum`) or `import enum` (`enum.Enum`).
fn imported(base: &Expr, reading: &Reading<'_>) -> Option<(String, String)> {
    let (root, attribute) = match base {
        Expr::Name(name) => (name.id.as_str(), None),
        Expr::Attribute(node) => match &*node.value {
            Expr::Name(name) => (name.id.as_str(), Some(node.attr.as_str())),
            _ => return None,
        },
        _ => return None,
    };
    if reading
        .enclosing
        .is_some_and(|held| held.names().contains(root))
    {
        return None;
    }
    reading.body.iter().find_map(|statement| {
        let start = statement.range().start();
        match (statement, attribute) {
            (Stmt::ImportFrom(node), None) if node.level == 0 => {
                let module = node.module.as_ref()?;
                node.names
                    .iter()
                    .find(|alias| alias.asname.as_ref().unwrap_or(&alias.name).as_str() == root)
                    .filter(|_| reading.bound.sole(root, start))
                    .map(|alias| (module.to_string(), alias.name.to_string()))
            }
            (Stmt::Import(node), Some(attribute)) => node
                .names
                .iter()
                .find(|alias| match &alias.asname {
                    Some(name) => name.as_str() == root,
                    None => alias.name.as_str() == root,
                })
                .filter(|_| reading.bound.sole(root, start))
                .map(|alias| (alias.name.to_string(), attribute.to_owned())),
            _ => None,
        }
    })
}
