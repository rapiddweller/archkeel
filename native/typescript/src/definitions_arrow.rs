// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Identify arrow scopes and default functions without a written declaration name.

use tree_sitter::Node;

use super::{place_of, DefinitionKind, Defs};
use crate::ancestors::{Entry, ERROR_ABOVE, INSIDE_NAMESPACE, IN_UNMODELED_BLOCK};
use crate::kinds::{F, K};
use crate::pytext::has_backslash;
use crate::tree::cx::Cx;

pub(super) fn callback(
    defs: &mut Defs,
    cx: &Cx,
    node: Node,
    stack: &[Entry],
    seen: u8,
) -> Option<u32> {
    if node.has_error()
        || cx.field(node, F::Parameters).is_none()
        || seen & (ERROR_ABOVE | INSIDE_NAMESPACE | IN_UNMODELED_BLOCK) != 0
        || stack
            .last()
            .is_none_or(|parent| parent.kind != K::Arguments || parent.shadow.ambiguous != 0)
        || Entry::ancestor_kind(stack, 2) != Some(K::CallExpression)
    {
        return None;
    }
    let span = cx.span(node);
    let name = format!("<callback:{}:{}>", span.line, span.column);
    let owner = stack.last().and_then(|entry| entry.scope);
    let parent = owner.and_then(|at| defs.scopes.0.get(at as usize).map(|scope| (at, scope)));
    let mut definition = Defs::build(
        cx,
        node,
        (name.clone(), DefinitionKind::Callback),
        parent,
        (stack, &place_of(stack)),
    );
    definition.top_level = false;
    definition.signature_complete = false;
    Some(defs.add_scope(name, owner, definition))
}

pub(super) fn name(cx: &Cx, node: Node, stack: &[Entry], seen: u8, top: bool) -> Option<String> {
    if node.has_error()
        || cx.field(node, F::Parameters).is_none()
        || seen & (ERROR_ABOVE | INSIDE_NAMESPACE | IN_UNMODELED_BLOCK) != 0
    {
        return None;
    }
    let declarator = stack.last().filter(|entry| {
        entry.kind == K::VariableDeclarator && cx.field(entry.node, F::Value) == Some(node)
    })?;
    let declaration = stack.get(stack.len().checked_sub(2)?)?;
    if declaration.kind != K::LexicalDeclaration
        || !cx
            .field(declaration.node, F::Kind)
            .is_some_and(|kind| cx.k(kind) == K::Const)
        || !top
    {
        return None;
    }
    let name = cx
        .field(declarator.node, F::Name)
        .filter(|name| cx.k(*name) == K::Identifier)?;
    let name = cx.text(name);
    if name.is_empty() || has_backslash(&name) {
        return None;
    }
    Some(name)
}

/// The direct anonymous default function, when no other route can reserve its export name.
pub(super) fn anonymous_default<'t>(cx: &Cx, top: &[Node<'t>]) -> Option<Node<'t>> {
    let mut routes = top.iter().copied().filter(|node| {
        cx.k(*node) == K::ExportStatement
            && (cx.has_child(*node, K::Default) || cx.field(*node, F::Declaration).is_none())
    });
    let export = routes.next()?;
    if !cx.has_child(export, K::Default) || routes.next().is_some() {
        return None;
    }
    let function = cx
        .field(export, F::Value)
        .or_else(|| cx.field(export, F::Declaration))?;
    let kind = cx.k(function);
    (matches!(kind, K::FunctionExpression | K::FunctionDeclaration)
        && cx.field(function, F::Name).is_none()
        && cx.field(function, F::Body).is_some())
    .then_some(function)
}
