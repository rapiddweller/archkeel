// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The depth of the tree that CPython builds for a module, read from the ruff tree.
//!
//! `source._ast_depth` counts the levels of `ast.iter_child_nodes`. A CPython tree has nodes that
//! ruff does not have (the context of a name, an operator, the empty `arguments` of a lambda, one
//! `If` for each `elif`, the `JoinedStr` of a format spec) and ruff has nodes that CPython does not
//! have (`Arguments`, `Decorator`, the parts of a string). This module maps one to the other. The walk keeps its own stack, so a
//! chain of a million `+` does not recurse.

use ruff_python_ast::visitor::source_order::{SourceOrderVisitor, TraversalSignal};
use ruff_python_ast::{AnyNodeRef, ModModule};

/// `_ast_depth` of the module: the root has depth 1.
pub fn depth(module: &ModModule) -> usize {
    let mut children = Children { nodes: Vec::new() };
    let mut stack = vec![Entry {
        node: AnyNodeRef::from(module),
        first: 0,
        open: false,
    }];
    let mut done: Vec<Done> = Vec::new();
    while let Some(entry) = stack.last_mut() {
        if !entry.open {
            entry.open = true;
            entry.first = done.len();
            let node = entry.node;
            if expands(node) {
                children.nodes.clear();
                node.visit_source_order(&mut children);
                let found = std::mem::take(&mut children.nodes);
                stack.extend(found.iter().rev().map(|child| Entry {
                    node: *child,
                    first: 0,
                    open: false,
                }));
                children.nodes = found;
            }
            continue;
        }
        let (node, first) = (entry.node, entry.first);
        stack.pop();
        let height = height(node, &done[first..]);
        done.truncate(first);
        done.push(Done {
            height,
            clause: clause(node),
        });
    }
    done.first().map_or(0, |root| root.height)
}

struct Entry<'a> {
    node: AnyNodeRef<'a>,
    first: usize,
    open: bool,
}

/// The height of a finished node, and whether it is an `elif` or an `else` of an `if`.
struct Done {
    height: usize,
    clause: Option<bool>,
}

/// The direct children of one node: the visitor takes each child and does not enter it.
struct Children<'a> {
    nodes: Vec<AnyNodeRef<'a>>,
}

impl<'a> SourceOrderVisitor<'a> for Children<'a> {
    fn enter_node(&mut self, node: AnyNodeRef<'a>) -> TraversalSignal {
        // A name of a definition, an attribute or an alias is a string field in CPython.
        if !matches!(node, AnyNodeRef::Identifier(_)) {
            self.nodes.push(node);
        }
        TraversalSignal::Skip
    }
}

/// A string or bytes literal is one `Constant` in CPython, whatever its parts.
fn expands(node: AnyNodeRef<'_>) -> bool {
    !matches!(
        node,
        AnyNodeRef::ExprStringLiteral(_) | AnyNodeRef::ExprBytesLiteral(_)
    )
}

/// `Some(true)` for an `elif`, `Some(false)` for an `else`.
fn clause(node: AnyNodeRef<'_>) -> Option<bool> {
    match node {
        AnyNodeRef::ElifElseClause(clause) => Some(clause.test.is_some()),
        _ => None,
    }
}

fn height(node: AnyNodeRef<'_>, children: &[Done]) -> usize {
    let deepest = children.iter().map(|child| child.height).max().unwrap_or(0);
    use AnyNodeRef as N;
    match node {
        // Wrappers that CPython does not have: their children are children of the parent.
        N::Arguments(_) | N::Decorator(_) | N::ParameterWithDefault(_) | N::TypeParams(_) => {
            deepest
        }
        N::PatternArguments(_) | N::PatternKeyword(_) | N::FString(_) | N::TString(_) => deepest,
        N::ElifElseClause(_) => deepest,
        // A context (`Load`, `Store`, `Del`) is a child node of height 1.
        N::ExprName(_) | N::ExprAttribute(_) | N::ExprSubscript(_) | N::ExprStarred(_) => {
            1 + deepest.max(1)
        }
        N::ExprList(_) | N::ExprTuple(_) => 1 + deepest.max(1),
        // So is an operator.
        N::ExprBinOp(_) | N::ExprUnaryOp(_) | N::ExprBoolOp(_) | N::ExprCompare(_) => {
            1 + deepest.max(1)
        }
        N::StmtAugAssign(_) => 1 + deepest.max(1),
        // A lambda without parameters still has an empty `arguments` node.
        AnyNodeRef::ExprLambda(lambda) if lambda.parameters.is_none() => 1 + deepest.max(1),
        AnyNodeRef::StmtIf(_) => 1 + if_chain(children),
        // ruff gives the parts of a format spec as children of the element; CPython holds them
        // in a `JoinedStr` of their own.
        AnyNodeRef::InterpolatedElement(element) => {
            let value = children.first().map_or(0, |child| child.height);
            let spec = element.format_spec.as_ref().map_or(0, |_| {
                let parts = children.iter().skip(1).map(|child| child.height).max();
                1 + parts.unwrap_or(0)
            });
            1 + value.max(spec)
        }
        _ => 1 + deepest,
    }
}

/// CPython nests each `elif` as an `If` in the `orelse` of the one before it.
fn if_chain(children: &[Done]) -> usize {
    let split = children
        .iter()
        .position(|child| child.clause.is_some())
        .unwrap_or(children.len());
    let (own, clauses) = children.split_at(split);
    let mut chain = 0;
    for clause in clauses.iter().rev() {
        chain = match clause.clause {
            Some(true) => 1 + clause.height.max(chain),
            _ => clause.height.max(chain),
        };
    }
    own.iter()
        .map(|child| child.height)
        .max()
        .unwrap_or(0)
        .max(chain)
}

#[cfg(test)]
#[path = "depth_tests.rs"]
mod tests;
