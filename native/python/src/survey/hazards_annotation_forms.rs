// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shapes of expressions that the annotation rules read (AD-1173): names, paths, aliases and
//! the parts of a subscript that are annotations.

use ruff_python_ast::{Expr, ExprSubscript, Identifier, Stmt};

use super::facts::NAMESPACES;

use crate::survey::typing_count::builtin;

/// A call of these makes a type form, not a string.
pub(super) const TYPE_FORMS: [&str; 7] = [
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

/// True when subscripting the standard `path` can give a type: a type or special form of a module
/// that holds only those, a builtin container, `type` or `os.PathLike`. Any other standard path
/// (`os.environ`) can be data, and `data[k]` can be a string.
pub(super) fn type_subscription(path: &str) -> bool {
    let module = path.rsplit_once('.').map_or("", |(module, _)| module);
    matches!(
        module,
        "typing"
            | "typing_extensions"
            | "collections.abc"
            | "collections"
            | "re"
            | "queue"
            | "contextlib"
            | "weakref"
    ) || builtin(path)
        || matches!(path, "type" | "os.PathLike")
}

/// A call of `globals`, `vars` or `locals`, or `x.__dict__`: the namespace of a module, a class or a frame.
pub(super) fn namespace(expr: &Expr) -> bool {
    match expr {
        Expr::Call(call) => {
            matches!(&*call.func, Expr::Name(n) if NAMESPACES.contains(&n.id.as_str()))
        }
        Expr::Attribute(node) => node.attr.as_str() == "__dict__",
        _ => false,
    }
}
