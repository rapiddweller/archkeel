// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that a scope below the module declares (AD-512).
//!
//! A site whose name has a declaration in an enclosing scope below the module is not bound to the
//! module symbol of that name. Release 4.0.1 hides only parameters, declarators and assignments, so
//! a local function, class, interface, type alias, enum, type parameter or catch binding did not
//! hide the module symbol. One walk finds the scope of each such name; every kind of site, and
//! each base of a class, asks the same index (`NameIndex::locally`).

use tree_sitter::Node;

use crate::ancestors::Entry;
use crate::kinds::{F, K};
use crate::tree::cx::Cx;

/// The kinds that a function declaration belongs to as a hoisted name.
fn function_like(kind: K) -> bool {
    matches!(
        kind,
        K::FunctionDeclaration
            | K::GeneratorFunctionDeclaration
            | K::FunctionExpression
            | K::GeneratorFunction
            | K::ArrowFunction
            | K::MethodDefinition
    )
}

/// The kinds that hold the lexical declarations of their body.
fn block_like(kind: K) -> bool {
    function_like(kind)
        || matches!(
            kind,
            K::StatementBlock | K::ClassStaticBlock | K::SwitchBody
        )
}

/// The range of the scope below the module that the name node `node` declares its name in, when
/// it declares one. `stack` holds the ancestors of the node, the parent last.
pub(crate) fn declared_in(cx: &Cx, node: Node, stack: &[Entry]) -> Option<(usize, usize)> {
    let parent = stack.last()?;
    let scope = match parent.kind {
        K::FunctionDeclaration | K::GeneratorFunctionDeclaration
            if cx.field(parent.node, F::Name) == Some(node) =>
        {
            hoisted(&stack[..stack.len() - 1])
        }
        K::ClassDeclaration
        | K::AbstractClassDeclaration
        | K::InterfaceDeclaration
        | K::TypeAliasDeclaration
        | K::EnumDeclaration
            if cx.field(parent.node, F::Name) == Some(node) =>
        {
            nearest(&stack[..stack.len() - 1], block_like)
        }
        // The name of a type parameter belongs to the declaration that owns the parameters.
        K::TypeParameter if cx.field(parent.node, F::Name) == Some(node) => stack
            .len()
            .checked_sub(3)
            .and_then(|at| stack.get(at))
            .map(|owner| owner.node),
        K::CatchClause if cx.field(parent.node, F::Parameter) == Some(node) => Some(parent.node),
        _ => None,
    }?;
    Some((scope.start_byte(), scope.end_byte()))
}

/// The nearest ancestor of a kind, unless the module comes first.
fn nearest<'t>(above: &[Entry<'t>], wanted: fn(K) -> bool) -> Option<Node<'t>> {
    for entry in above.iter().rev() {
        if entry.kind == K::Program {
            return None;
        }
        if wanted(entry.kind) {
            return Some(entry.node);
        }
    }
    None
}

/// A function declaration is hoisted to its function; without one, to its block.
fn hoisted<'t>(above: &[Entry<'t>]) -> Option<Node<'t>> {
    nearest(above, function_like).or_else(|| nearest(above, block_like))
}
