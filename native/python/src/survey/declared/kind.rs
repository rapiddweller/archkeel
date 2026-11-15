// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The kind of a class that Python binds when the class statement runs (AD-518, rule 6).
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

/// A class of the module body with a record: its kind, and whether `A()` gives an instance of it
/// (no enum, no protocol, no `__new__` in it or in a local base).
#[derive(Clone, Copy, Debug)]
pub(super) struct Local {
    pub kind: Kind,
    pub constructible: bool,
}

/// One base of a class: its expression, the qualified name that it resolves to, and whether that
/// is a protocol class of the module (then a class that is no protocol realizes it).
pub(super) struct BaseSite<'a> {
    pub expr: &'a Expr,
    pub target: String,
    pub protocol: bool,
}

/// The proven kind and bases of a class.
pub(super) struct Class<'a> {
    pub kind: Kind,
    pub bases: Vec<BaseSite<'a>>,
    /// Each base lets `A()` give an instance of `A`.
    pub constructible: bool,
}

/// What a class statement reads to know its bases.
pub(super) struct Reading<'a> {
    pub module: &'a str,
    pub body: &'a [Stmt],
    pub bound: &'a Bound,
    pub binders: &'a Binders,
    /// The class body that holds this class, for a nested class: it can bind a name of a base.
    pub enclosing: Option<&'a Bound>,
    /// The classes of the module body that have a record, by name (a top-level class only).
    pub local: &'a HashMap<String, Local>,
}

impl<'a> Reading<'a> {
    /// The reading of a class of the module body.
    pub(super) fn top(
        (module, body): (&'a str, &'a [Stmt]),
        bound: &'a Bound,
        binders: &'a Binders,
        local: &'a HashMap<String, Local>,
    ) -> Self {
        Reading {
            module,
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
enum Is {
    Plain,
    Protocol,
    Enum,
}

/// What `classify` finds for one base.
struct Found {
    is: Is,
    target: String,
    protocol: bool,
    constructible: bool,
}

/// The kind and the bases of `node`, or `None` when a base or a keyword leaves them open.
pub(super) fn of<'a>(node: &'a StmtClassDef, reading: &Reading<'_>) -> Option<Class<'a>> {
    if node.type_params.is_some() {
        return None;
    }
    let arguments = node.arguments.as_deref();
    if arguments.is_some_and(|arguments| !arguments.keywords.is_empty()) {
        return None;
    }
    let (mut protocol, mut enumeration, mut constructible) = (false, false, true);
    let mut bases = Vec::new();
    for base in arguments.map_or(&[][..], |arguments| &arguments.args) {
        let found = classify(base, reading)?;
        match found.is {
            Is::Plain => {}
            Is::Protocol => protocol = true,
            Is::Enum => enumeration = true,
        }
        constructible &= found.constructible;
        bases.push(BaseSite {
            expr: base,
            target: found.target,
            protocol: found.protocol,
        });
    }
    let kind = match (protocol, enumeration) {
        (true, true) => return None,
        (true, false) => Kind::Protocol,
        (false, true) => Kind::Enum,
        (false, false) => Kind::Plain,
    };
    Some(Class {
        kind,
        bases,
        constructible,
    })
}

fn classify(base: &Expr, reading: &Reading<'_>) -> Option<Found> {
    if let Expr::Name(name) = base {
        let name = name.id.as_str();
        if reading
            .enclosing
            .is_some_and(|held| held.names().contains(name))
        {
            return None;
        }
        if let Some(local) = reading
            .local
            .get(name)
            .filter(|_| reading.enclosing.is_none())
        {
            // A class that derives from a protocol class is no protocol itself.
            return Some(Found {
                is: match local.kind {
                    Kind::Enum => Is::Enum,
                    Kind::Plain | Kind::Protocol => Is::Plain,
                },
                target: format!("{}.{name}", reading.module),
                protocol: local.kind == Kind::Protocol,
                constructible: local.constructible,
            });
        }
        if BUILTIN_BASES.contains(&name) && reading.binders.builtin_visible(name) {
            return Some(Found {
                is: Is::Plain,
                target: format!("builtins.{name}"),
                protocol: false,
                constructible: true,
            });
        }
    }
    let (module, symbol) = imported(base, reading)?;
    let is = match (module.as_str(), symbol.as_str()) {
        ("typing" | "typing_extensions", "Protocol") => Is::Protocol,
        ("enum", symbol) if ENUM_BASES.contains(&symbol) => Is::Enum,
        _ => return None,
    };
    Some(Found {
        is,
        target: format!("{module}.{symbol}"),
        protocol: false,
        constructible: false,
    })
}

/// The module and the name that an expression reads through the one plain import of its root:
/// `from enum import Enum` (`Enum`) or `import enum` (`enum.Enum`).
pub(super) fn imported(base: &Expr, reading: &Reading<'_>) -> Option<(String, String)> {
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
