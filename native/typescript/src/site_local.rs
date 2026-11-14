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
use crate::scope::assignment_targets;
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

/// The identifiers that a pattern, a parameter or an assignment target names: the one place that
/// reads a pattern (`assignment_targets` walks shorthand, renamed, array, rest, default and nested
/// forms). A target that is no plain name, such as `a.b`, names nothing.
pub(crate) fn pattern_names<'t>(cx: &Cx, pattern: Node<'t>) -> Vec<Node<'t>> {
    assignment_targets(cx, pattern)
        .into_iter()
        .filter(|found| {
            matches!(
                cx.k(*found),
                K::Identifier | K::TypeIdentifier | K::ShorthandPropertyIdentifierPattern
            )
        })
        .collect()
}

/// The names that the declaration `node` binds, and the range of the scope below the module that
/// holds them. `stack` holds the ancestors of the node, the parent last.
pub(crate) fn declared_in<'t>(
    cx: &Cx,
    node: Node<'t>,
    kind: K,
    stack: &[Entry<'t>],
) -> Option<(Vec<Node<'t>>, (usize, usize))> {
    let names = |field: F| cx.field(node, field).map(|found| pattern_names(cx, found));
    let (names, scope) = match kind {
        K::RequiredParameter | K::OptionalParameter => {
            (names(F::Pattern), nearest(stack, function_like))
        }
        K::CatchClause => (names(F::Parameter), Some(node)),
        // A `for` head that declares (`const`, `let`, `var`) binds in the statement.
        K::ForInStatement if cx.field(node, F::Kind).is_some() => (names(F::Left), Some(node)),
        K::VariableDeclarator => (names(F::Name), hoisted(stack)),
        K::FunctionDeclaration | K::GeneratorFunctionDeclaration => {
            (names(F::Name), hoisted(stack))
        }
        K::ClassDeclaration
        | K::AbstractClassDeclaration
        | K::InterfaceDeclaration
        | K::TypeAliasDeclaration
        | K::EnumDeclaration
        | K::InternalModule => (names(F::Name), nearest(stack, block_like)),
        // The name of a type parameter belongs to the declaration that owns the parameters.
        K::TypeParameter => (
            names(F::Name),
            stack
                .len()
                .checked_sub(2)
                .and_then(|at| stack.get(at))
                .map(|owner| owner.node),
        ),
        _ => (None, None),
    };
    let scope = scope?;
    Some((names?, (scope.start_byte(), scope.end_byte())))
}

/// The names that the node writes: the declarator of a variable, the target of an assignment of
/// any operator, of `++` and `--`, and the head of a `for` loop that declares nothing. The value
/// of a name that is written more than once is not the value of its first write.
pub(crate) fn written_by<'t>(cx: &Cx, node: Node<'t>, kind: K) -> Vec<Node<'t>> {
    let target = match kind {
        K::VariableDeclarator => cx.field(node, F::Name),
        K::AssignmentExpression | K::AugmentedAssignmentExpression => cx.field(node, F::Left),
        K::UpdateExpression => cx.field(node, F::Argument),
        K::ForInStatement if cx.field(node, F::Kind).is_none() => cx.field(node, F::Left),
        _ => None,
    };
    target.map_or_else(Vec::new, |found| pattern_names(cx, found))
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
