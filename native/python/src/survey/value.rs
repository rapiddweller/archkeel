// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the value of a module-level assignment reads, when it can hold no module (AD-530).
//!
//! A name of a package that another module imports and uses as a value escapes the package
//! (`uses.rs`), because the value might be a module of the scan. A value that is built only from
//! constants, from the builtin constructors `tuple`, `list`, `set`, `frozenset`, `dict`, `sorted`
//! and the scalar builtins, from names, and from `.keys()`, `.values()` and `.items()` of such a
//! value, holds a module only if one of its names does. `Deps` lists those names and builtins;
//! `uses.rs` decides each of them. Any other form (a call, an attribute, a subscript, an
//! operator, a comprehension, a starred item) is no value of this kind.

use crate::module::builtin_roles::{self, Role};
use ruff_python_ast::{Expr, ExprCall, Stmt};

/// The names and the builtins that a value reads.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub(super) struct Deps {
    /// Names of the module scope: each must be inert for the value to be inert.
    pub names: Vec<String>,
    /// Builtin functions that the value calls: the module must not bind them.
    pub builtins: Vec<&'static str>,
}

/// What `value` reads, or `None` when it can hold a module that it does not name.
pub(super) fn value_deps(value: &Expr) -> Option<Deps> {
    let mut deps = Deps::default();
    read(value, &mut deps).then_some(deps)
}

fn read(value: &Expr, deps: &mut Deps) -> bool {
    match value {
        Expr::StringLiteral(_)
        | Expr::BytesLiteral(_)
        | Expr::NumberLiteral(_)
        | Expr::BooleanLiteral(_)
        | Expr::NoneLiteral(_)
        | Expr::EllipsisLiteral(_)
        | Expr::FString(_)
        | Expr::Lambda(_) => true,
        Expr::Name(name) => {
            deps.names.push(name.id.to_string());
            true
        }
        Expr::Tuple(node) => node.elts.iter().all(|item| read(item, deps)),
        Expr::List(node) => node.elts.iter().all(|item| read(item, deps)),
        Expr::Set(node) => node.elts.iter().all(|item| read(item, deps)),
        Expr::Dict(node) => node.items.iter().all(|item| {
            // `{**other}` has no key: the value is no plain display.
            item.key.as_ref().is_some_and(|key| read(key, deps)) && read(&item.value, deps)
        }),
        Expr::Call(call) => call_value(call, deps),
        _ => false,
    }
}

/// A call of a builtin constructor, or `.keys()`, `.values()` and `.items()` of a value.
fn call_value(call: &ExprCall, deps: &mut Deps) -> bool {
    let args = &call.arguments;
    match &*call.func {
        Expr::Name(name) => {
            let id = name.id.as_str();
            if let Some(scalar) =
                builtin_roles::named(Role::SCALAR_CALL).find(|candidate| *candidate == id)
            {
                deps.builtins.push(scalar);
                return true;
            }
            let Some(container) =
                builtin_roles::named(Role::CONTAINER_CALL).find(|candidate| *candidate == id)
            else {
                return false;
            };
            deps.builtins.push(container);
            let plain = args.keywords.iter().all(|keyword| keyword.arg.is_some());
            plain
                && args.args.iter().all(|item| read(item, deps))
                && args
                    .keywords
                    .iter()
                    .all(|keyword| read(&keyword.value, deps))
        }
        Expr::Attribute(node) => {
            let view = matches!(node.attr.as_str(), "keys" | "values" | "items");
            view && args.is_empty() && read(&node.value, deps)
        }
        _ => false,
    }
}

/// The targets and the value of a plain or annotated assignment; `None` for any other statement.
pub(super) fn assignment_parts(stmt: &Stmt) -> Option<(Vec<&Expr>, Option<&Expr>)> {
    match stmt {
        Stmt::Assign(node) => Some((node.targets.iter().collect(), Some(&node.value))),
        Stmt::AnnAssign(node) => Some((vec![&*node.target], node.value.as_deref())),
        _ => None,
    }
}
