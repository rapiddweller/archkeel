// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the value of a module-scope assignment binds its name to (`bound.rs`, AD-566): a value, a
//! builtin generic, a call of a plain name, or an unknown object.

use ruff_python_ast::Expr;

/// What the statement of a site binds the name to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Kind {
    /// A `def` or a `class`: the name is a function or a class, never a module.
    Callable,
    /// A display or literal makes a value, not a module.
    Value,
    /// A subscript of a builtin generic, if the module does not bind that builtin.
    BuiltinGeneric(&'static str),
    /// A call of a plain name: the value is an instance when that name is a bare class (AD-566).
    Call,
    /// An import: the name is whatever the imported name is.
    Import,
    /// A plain assignment of a name, or of a builtin call, that `value_kind` does not take as a
    /// value (`value.rs`, AD-530): `Bound::deps` says what it reads.
    Derived,
    /// Any other binder: the value is unknown.
    Other,
}

/// True for a literal of a number, a string, bytes, a boolean or `None`.
pub(super) fn scalar_literal(value: &Expr) -> bool {
    matches!(
        value,
        Expr::NumberLiteral(_)
            | Expr::StringLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::NoneLiteral(_)
    )
}

/// The builtin types whose call makes an instance of that type, never another object.
const BUILTIN_VALUES: [&str; 10] = [
    "list",
    "dict",
    "tuple",
    "set",
    "frozenset",
    "int",
    "str",
    "float",
    "bool",
    "bytes",
];

/// True for arithmetic over number literals: its value is a number.
fn number_arithmetic(value: &Expr) -> bool {
    match value {
        Expr::NumberLiteral(_) => true,
        Expr::UnaryOp(node) => number_arithmetic(&node.operand),
        Expr::BinOp(node) => number_arithmetic(&node.left) && number_arithmetic(&node.right),
        _ => false,
    }
}

/// The kind of the value of an assignment, and the callee name of a call of a plain name.
pub(super) fn value_kind(value: &Expr) -> (Kind, Option<&str>) {
    if let Expr::Call(call) = value {
        if let Expr::Name(name) = &*call.func {
            let name = name.id.as_str();
            if let Some(builtin) = BUILTIN_VALUES.iter().find(|builtin| **builtin == name) {
                return (Kind::BuiltinGeneric(builtin), None);
            }
            return (Kind::Call, Some(name));
        }
    }
    if number_arithmetic(value) && !matches!(value, Expr::NumberLiteral(_)) {
        return (Kind::Value, None);
    }
    (plain_kind(value), None)
}

fn plain_kind(value: &Expr) -> Kind {
    if let Expr::Subscript(subscript) = value {
        if let Expr::Name(name) = &*subscript.value {
            let builtin = match name.id.as_str() {
                "list" => Some("list"),
                "dict" => Some("dict"),
                "tuple" => Some("tuple"),
                "set" => Some("set"),
                "frozenset" => Some("frozenset"),
                "type" => Some("type"),
                _ => None,
            };
            if let Some(builtin) = builtin {
                return Kind::BuiltinGeneric(builtin);
            }
        }
    }
    if scalar_literal(value)
        || matches!(
            value,
            Expr::Tuple(_) | Expr::List(_) | Expr::Dict(_) | Expr::Set(_) | Expr::FString(_)
        )
    {
        Kind::Value
    } else {
        Kind::Other
    }
}
