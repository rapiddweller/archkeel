// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The dynamic namespace exposures of `source.py`: `resolve_static_name`,
//! `exposes_dynamic_namespace` without the member surface, `reads_only_namespace_names` and
//! `_consumed_as_names` (AD-273, AD-275).
//!
//! The parents of a node are the stack of a source-order walk. Ruff puts an `Arguments` node
//! between a call and its arguments, where Python has none; `consumed_as_names` reads through it.

use ruff_python_ast::{AnyNodeRef, CmpOp, Expr, ExprAttribute, ExprContext};

use super::binders::Binders;
use super::imports::Aliases;

use crate::module::namespace_tables::{CONTAINERS, GLOBAL, GLOBALS, LOCAL};

/// `resolve_static_name` of a name or a name-rooted attribute. Any other node has the text of
/// `ast.unparse`, which never equals one of the names above, so it is `None`.
pub fn resolve(expr: &Expr, aliases: &Aliases) -> Option<String> {
    match expr {
        Expr::Attribute(node) => resolve_attribute(node, aliases),
        Expr::Name(node) => Some(alias_of(&node.id, aliases).to_owned()),
        _ => None,
    }
}

fn alias_of<'t>(id: &'t str, aliases: &'t Aliases) -> &'t str {
    aliases.get(id).map_or(id, |alias| alias.target.as_str())
}

fn resolve_attribute(node: &ExprAttribute, aliases: &Aliases) -> Option<String> {
    let mut attributes = vec![node.attr.as_str()];
    let mut current = &*node.value;
    while let Expr::Attribute(node) = current {
        attributes.push(node.attr.as_str());
        current = &node.value;
    }
    let Expr::Name(root) = current else {
        return None;
    };
    let mut text = alias_of(&root.id, aliases).to_owned();
    for attribute in attributes.iter().rev() {
        text.push('.');
        text.push_str(attribute);
    }
    Some(text)
}

/// How a node exposes the namespace (`exposes_dynamic_namespace` with `local_namespace` false
/// and true, `include_import_effects` true).
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Exposure {
    None,
    /// An exposure in each scope.
    Global,
    /// An exposure only when the node is evaluated at module scope.
    Local,
}

pub fn exposure(node: AnyNodeRef, aliases: &Aliases) -> Exposure {
    let (target, reads) = match node {
        AnyNodeRef::ExprCall(call) => (&*call.func, call.arguments.args.is_empty()),
        AnyNodeRef::StmtAssign(assign) if is_reference(&assign.value) => (&*assign.value, true),
        AnyNodeRef::StmtAnnAssign(assign) => match assign.value.as_deref() {
            Some(value) if is_reference(value) => (value, true),
            _ => return Exposure::None,
        },
        AnyNodeRef::ExprName(name) if name.ctx == ExprContext::Load => {
            return classify(alias_of(&name.id, aliases), true)
        }
        AnyNodeRef::ExprAttribute(attribute) if attribute.ctx == ExprContext::Load => {
            return attribute_exposure(attribute, aliases)
        }
        _ => return Exposure::None,
    };
    let Some(name) = resolve(target, aliases) else {
        return Exposure::None;
    };
    classify(&name, reads)
}

fn is_reference(value: &Expr) -> bool {
    matches!(value, Expr::Name(_) | Expr::Attribute(_))
}

fn attribute_exposure(attribute: &ExprAttribute, aliases: &Aliases) -> Exposure {
    // A resolved attribute ends with its own name, so only these names can match.
    let attr = attribute.attr.as_str();
    let last = |name: &&str| name.rsplit('.').next() == Some(attr);
    if !GLOBAL.iter().chain(&LOCAL).any(last) {
        return Exposure::None;
    }
    resolve_attribute(attribute, aliases).map_or(Exposure::None, |name| classify(&name, true))
}

fn classify(name: &str, reads: bool) -> Exposure {
    if GLOBAL.contains(&name) {
        Exposure::Global
    } else if reads && LOCAL.contains(&name) {
        Exposure::Local
    } else {
        Exposure::None
    }
}

/// The node that `_namespace_may_rebind` judges, and its parents: the call of a callee, else the
/// node itself. `parents` ends with the parent of `node`.
pub fn reads_only<'a>(
    node: AnyNodeRef<'a>,
    parents: &[AnyNodeRef<'a>],
    aliases: &Aliases,
    binders: &Binders,
) -> bool {
    let (read, parents) = match parents.split_last() {
        Some((AnyNodeRef::ExprCall(call), rest)) if AnyNodeRef::from(&*call.func).ptr_eq(node) => {
            (AnyNodeRef::ExprCall(call), rest)
        }
        _ => (node, parents),
    };
    let AnyNodeRef::ExprCall(call) = read else {
        return false;
    };
    call.arguments.args.is_empty()
        && resolve(&call.func, aliases).is_some_and(|name| GLOBALS.contains(&name.as_str()))
        && consumed_as_names(read, parents, binders)
}

/// `_consumed_as_names`: the dict reaches only a consumer of its keys as strings.
fn consumed_as_names(node: AnyNodeRef, parents: &[AnyNodeRef], binders: &Binders) -> bool {
    let Some((parent, rest)) = parents.split_last() else {
        return false;
    };
    match parent {
        AnyNodeRef::ExprAttribute(attribute) if attribute.attr.as_str() == "keys" => {
            match rest.split_last() {
                Some((call @ AnyNodeRef::ExprCall(inner), rest))
                    if AnyNodeRef::from(&*inner.func).ptr_eq(*parent) =>
                {
                    consumed_as_names(*call, rest, binders)
                }
                _ => false,
            }
        }
        AnyNodeRef::Arguments(arguments) => match rest.last() {
            Some(AnyNodeRef::ExprCall(call)) => {
                arguments.args.len() == 1
                    && AnyNodeRef::from(&arguments.args[0]).ptr_eq(node)
                    && bare_builtin(&call.func, binders)
            }
            _ => false,
        },
        AnyNodeRef::ExprCompare(compare) => {
            compare
                .comparators()
                .last()
                .is_some_and(|last| AnyNodeRef::from(last).ptr_eq(node))
                && matches!(compare.ops.last(), Some(CmpOp::In | CmpOp::NotIn))
        }
        AnyNodeRef::StmtFor(statement) => AnyNodeRef::from(&*statement.iter).ptr_eq(node),
        AnyNodeRef::Comprehension(comprehension) => {
            AnyNodeRef::from(&comprehension.iter).ptr_eq(node)
        }
        _ => false,
    }
}

/// `_bare_builtin` of `_NAME_CONTAINERS`: a module-level `def set(...)` is not the builtin.
fn bare_builtin(func: &Expr, binders: &Binders) -> bool {
    matches!(func, Expr::Name(name)
        if CONTAINERS.contains(&name.id.as_str()) && binders.builtin_visible(name.id.as_str()))
}

#[cfg(test)]
#[path = "namespace_tests.rs"]
mod tests;
