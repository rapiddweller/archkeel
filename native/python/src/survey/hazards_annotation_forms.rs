// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shapes of expressions that the annotation rules read (AD-1173): names, paths, aliases and
//! the parts of a subscript that are annotations.

use ruff_python_ast::{
    Expr, ExprCall, ExprList, ExprSubscript, ExprTuple, Identifier, Operator, Stmt,
};

/// A call of these makes a type form, not a string.
const TYPE_FORMS: [&str; 7] = [
    "TypeVar",
    "ParamSpec",
    "TypeVarTuple",
    "NewType",
    "TypeAliasType",
    "namedtuple",
    "Enum",
];

/// True for `Literal` and `typing.Literal`: its strings are values, no annotation.
pub(in crate::survey::hazards) fn literal(value: &Expr) -> bool {
    named(value, "Literal")
}

pub(super) fn named(value: &Expr, name: &str) -> bool {
    match value {
        Expr::Name(node) => node.id.as_str() == name,
        Expr::Attribute(node) => Identifier::as_str(&node.attr) == name,
        _ => false,
    }
}

pub(super) fn last(expr: &Expr) -> Option<&str> {
    match expr {
        Expr::Name(node) => Some(node.id.as_str()),
        Expr::Attribute(node) => Some(Identifier::as_str(&node.attr)),
        _ => None,
    }
}

/// Each `target = value` of a statement: an assignment, or an annotated assignment with a value.
pub(super) fn assigned<'a>(stmt: &'a Stmt, mut each: impl FnMut(&'a Expr, &'a Expr)) {
    match stmt {
        Stmt::Assign(node) => node.targets.iter().for_each(|t| each(t, &node.value)),
        Stmt::AnnAssign(node) => node.value.iter().for_each(|v| each(&node.target, v)),
        _ => {}
    }
}

/// A name, an attribute path, a subscript of one, or a union of them: a type form alias. A string
/// inside the subscript is no type form: Python evaluates it when it reads the alias.
pub(super) fn path(value: &Expr) -> bool {
    match value {
        Expr::Name(_) | Expr::NoneLiteral(_) => true,
        Expr::Attribute(node) => path(&node.value),
        Expr::Subscript(node) => {
            path(&node.value) && (literal(&node.value) || items(node).into_iter().all(typeish))
        }
        Expr::BinOp(node) => node.op == Operator::BitOr && path(&node.left) && path(&node.right),
        _ => false,
    }
}

fn typeish(value: &Expr) -> bool {
    match value {
        Expr::Tuple(node) => node.elts.iter().all(typeish),
        Expr::List(node) => node.elts.iter().all(typeish),
        Expr::NumberLiteral(_) | Expr::BooleanLiteral(_) | Expr::EllipsisLiteral(_) => true,
        other => path(other),
    }
}

/// The parts of a subscript that are annotations: the metadata of `Annotated` is none.
pub(super) fn items(node: &ExprSubscript) -> Vec<&Expr> {
    let all = match &*node.slice {
        Expr::Tuple(tuple) => tuple.elts.iter().collect(),
        one => vec![one],
    };
    let count = if named(&node.value, "Annotated") {
        1
    } else {
        all.len()
    };
    all.into_iter().take(count).collect()
}

/// The names that a path holds: each attribute name and the root name.
pub(super) fn ids(value: &Expr, out: &mut Vec<String>) {
    match value {
        Expr::Name(node) => out.push(node.id.to_string()),
        Expr::Attribute(node) => {
            out.push(node.attr.to_string());
            ids(&node.value, out);
        }
        Expr::Subscript(node) => {
            ids(&node.value, out);
            items(node).into_iter().for_each(|i| ids(i, out));
        }
        Expr::Tuple(ExprTuple { elts, .. }) | Expr::List(ExprList { elts, .. }) => {
            for elt in elts {
                ids(elt, out);
            }
        }
        Expr::BinOp(node) => [&node.left, &node.right].iter().for_each(|e| ids(e, out)),
        _ => {}
    }
}

/// A value that is no string the survey could miss: a literal, a type factory, a function.
pub(super) fn inert(value: &Expr) -> bool {
    let made = |call: &ExprCall| last(&call.func).is_some_and(|name| TYPE_FORMS.contains(&name));
    match value {
        Expr::Call(call) => made(call),
        Expr::Lambda(_) => true,
        other => constant(other),
    }
}

fn constant(value: &Expr) -> bool {
    matches!(
        value,
        Expr::StringLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::EllipsisLiteral(_)
    )
}
