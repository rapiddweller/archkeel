// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Identify definition forms without reading or creating definition records.

use tree_sitter::Node;

use crate::ancestors::{Entry, ERROR_ABOVE, INSIDE_NAMESPACE, IN_UNMODELED_BLOCK};
use crate::kinds::{F, K};
use crate::pytext::has_backslash;
use crate::tree::cx::Cx;
use crate::tree::nodes::{children, named_children};

pub(super) fn module_array_constant(
    cx: &Cx,
    node: Node,
    value: Node,
    stack: &[Entry],
    seen: u8,
) -> bool {
    if node.has_error() || seen & ERROR_ABOVE != 0 || !Entry::top_of_file(stack, 2) {
        return false;
    }
    let mut value = value;
    if cx.k(value) == K::AsExpression {
        let parts: Vec<Node> = children(value)
            .into_iter()
            .filter(|item| cx.k(*item) != K::Comment)
            .collect();
        if parts.len() != 3 || cx.k(parts[1]) != K::As || cx.k(parts[2]) != K::Const {
            return false;
        }
        value = parts[0];
    }
    cx.k(value) == K::Array
        && named_children(value).into_iter().all(|item| {
            matches!(
                cx.k(item),
                K::Identifier | K::String | K::Number | K::True | K::False | K::Null | K::Comment
            )
        })
}

pub(super) fn callback(cx: &Cx, node: Node, stack: &[Entry], seen: u8) -> Option<String> {
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
    Some(format!("<callback:{}:{}>", span.line, span.column))
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
