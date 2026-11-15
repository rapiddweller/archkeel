// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that TypeScript binds at run time and that no declarator shows: an `enum`, a
//! `namespace` with a value, and the `arguments` object of a function. The walk (`walk.rs`) and
//! the script tree (`script_bind.rs`) ask the same questions, so the answers live here.
//!
//! A binding is real only where the run time creates one. A `declare` of a name is a type of a
//! value that lives elsewhere: it binds nothing. A `namespace` that holds only types has no run
//! time object. `arguments` belongs to each function that is no arrow; an arrow takes the one
//! of the function around it, and a module has none (AD-534).

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::tree::cx::Cx;
use crate::tree::nodes::named_children;

/// The implicit name that each function that is no arrow binds.
pub(crate) const ARGUMENTS: &str = "arguments";

/// Whether a function of this kind owns an `arguments` object.
pub(crate) fn owns_arguments(kind: K) -> bool {
    matches!(
        kind,
        K::FunctionDeclaration
            | K::FunctionExpression
            | K::GeneratorFunctionDeclaration
            | K::GeneratorFunction
            | K::MethodDefinition
    )
}

/// The name node that an `enum` or a `namespace` binds in the scope around it, or `None` where
/// it binds nothing. `ambient` is true under a `declare`.
pub(crate) fn runtime_name<'t>(
    cx: &Cx,
    node: Node<'t>,
    kind: K,
    ambient: bool,
) -> Option<Node<'t>> {
    if ambient {
        return None;
    }
    match kind {
        K::EnumDeclaration => cx.field(node, F::Name),
        K::InternalModule | K::Module => {
            let name = first_name(cx, cx.field(node, F::Name)?);
            (cx.k(name) == K::Identifier && holds_value(cx, node)).then_some(name)
        }
        _ => None,
    }
}

/// `A` of `namespace A.B.C {}`.
fn first_name<'t>(cx: &Cx, mut name: Node<'t>) -> Node<'t> {
    while cx.k(name) == K::NestedIdentifier {
        match name.named_child(0) {
            Some(first) => name = first,
            None => break,
        }
    }
    name
}

/// Whether the body of a namespace has a member that exists at run time.
fn holds_value(cx: &Cx, namespace: Node) -> bool {
    cx.field(namespace, F::Body).is_some_and(|body| {
        named_children(body)
            .into_iter()
            .any(|item| is_value(cx, item))
    })
}

/// A statement of a namespace that makes it a run time object. A const enum, an interface, a type
/// alias, an alias of an import and a `declare` leave no trace. A statement that this list does
/// not know counts as no value: the name stays free, as before.
fn is_value(cx: &Cx, statement: Node) -> bool {
    match cx.k(statement) {
        K::LexicalDeclaration
        | K::VariableDeclaration
        | K::FunctionDeclaration
        | K::GeneratorFunctionDeclaration
        | K::ClassDeclaration
        | K::AbstractClassDeclaration
        | K::ExpressionStatement
        | K::IfStatement
        | K::ForStatement
        | K::ForInStatement => true,
        K::EnumDeclaration => !cx.has_child(statement, K::Const),
        K::InternalModule | K::Module => holds_value(cx, statement),
        K::ExportStatement => cx
            .field(statement, F::Declaration)
            .is_some_and(|declaration| is_value(cx, declaration)),
        _ => false,
    }
}

#[cfg(test)]
#[path = "bind_kinds_tests.rs"]
mod tests;
