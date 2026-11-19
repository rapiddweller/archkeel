// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

impl Defs {
    pub(super) fn arrow(&mut self, cx: &Cx, node: Node, stack: &[Entry], seen: u8) -> Option<u32> {
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
            || !top_of_file(stack, 3)
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
        let place = place_of(stack);
        let mut definition = Self::build(
            cx,
            node,
            (name.clone(), DefinitionKind::Function),
            None,
            (stack, &place),
        );
        definition.exported = ancestor_kind(stack, 3) == Some(K::ExportStatement);
        definition.top_level = true;
        definition.overload_signature = false;
        definition.signature_complete = false;
        self.scopes.0.push(Scope {
            name,
            parent: None,
            line: definition.span.line,
            column: definition.span.column,
        });
        self.found.push(definition);
        Some((self.scopes.0.len() - 1) as u32)
    }
}
