// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Identify the binding of a module-level const arrow.

use tree_sitter::Node;

use crate::ancestors::{Entry, ERROR_ABOVE, INSIDE_NAMESPACE, IN_UNMODELED_BLOCK};
use crate::kinds::{F, K};
use crate::pytext::has_backslash;
use crate::tree::cx::Cx;

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
