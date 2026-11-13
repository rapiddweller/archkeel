// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The questions that `sites.rs` asks about one node and its nearest ancestors.
//!
//! Each question reads the node, its parent and its grandparent from the stack of the walk, as
//! `parse.py` reads `node.parent`. None of them climbs further, so none costs more than the node
//! has relatives of its own.

use tree_sitter::Node;

use crate::ancestors::Entry;
use crate::kinds::{F, K};
use crate::site_paths::{is_script_root, Text};
use crate::tree::cx::Cx;
use crate::tree::nodes::named_children;

/// `_TYPE_PARENTS`.
pub(crate) fn holds_types(kind: K) -> bool {
    matches!(
        kind,
        K::TypeAnnotation
            | K::TypeArguments
            | K::TypeQuery
            | K::TypeAliasDeclaration
            | K::TypeParameter
            | K::ExtendsTypeClause
            | K::ImplementsClause
    )
}

pub(crate) fn is_function_scope(kind: K) -> bool {
    matches!(
        kind,
        K::ArrowFunction | K::FunctionExpression | K::GeneratorFunction
    )
}

pub(crate) fn is_reference_kind(kind: K) -> bool {
    matches!(
        kind,
        K::Identifier | K::TypeIdentifier | K::PropertyIdentifier | K::ShorthandPropertyIdentifier
    )
}

/// `_target_name`: the name and the receiver that a call or a reference spells.
pub(crate) struct Target {
    pub name: Option<Text>,
    pub receiver: Option<Text>,
    pub computed: bool,
    pub receiver_kind: ReceiverKind,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ReceiverKind {
    None,
    This,
    Other,
}

/// The node of the parent entry and of the grandparent entry of the node that the walk enters.
pub(crate) fn relatives<'a, 't>(
    stack: &'a [Entry<'t>],
) -> (Option<&'a Entry<'t>>, Option<&'a Entry<'t>>) {
    let parent = stack.last();
    let grand = stack.len().checked_sub(2).and_then(|at| stack.get(at));
    (parent, grand)
}

/// `_target_name`.
pub(crate) fn target_name(cx: &Cx, node: Node) -> Target {
    match cx.k(node) {
        K::Identifier | K::TypeIdentifier => Target {
            name: Some(Text::of(node)),
            receiver: None,
            computed: false,
            receiver_kind: ReceiverKind::None,
        },
        K::MemberExpression => {
            let receiver = cx.field(node, F::Object);
            let property = cx.field(node, F::Property);
            let plain = property.filter(|item| cx.k(*item) == K::PropertyIdentifier);
            Target {
                name: plain.map(Text::of),
                receiver: receiver.map(Text::of),
                computed: plain.is_none(),
                receiver_kind: match receiver {
                    Some(item) if cx.k(item) == K::This => ReceiverKind::This,
                    Some(_) => ReceiverKind::Other,
                    None => ReceiverKind::None,
                },
            }
        }
        _ => Target {
            name: None,
            receiver: None,
            computed: true,
            receiver_kind: ReceiverKind::None,
        },
    }
}

/// `_declaration_name`: the node is the name that its parent declares.
pub(crate) fn declaration_name(cx: &Cx, node: Node, parent: Option<&Entry>) -> bool {
    let Some(parent) = parent else {
        return false;
    };
    [F::Name, F::Pattern, F::Alias]
        .into_iter()
        .any(|field| cx.field(parent.node, field) == Some(node))
        || parent.kind == K::NamespaceExport
        || (parent.kind == K::PairPattern && cx.field(parent.node, F::Key) == Some(node))
}

/// `_is_jsx_attribute_name`: the name of an attribute, or the namespace name that holds it.
fn jsx_attribute_name(node: Node, parent: &Entry, grand: Option<&Entry>) -> bool {
    let namespaced = parent.kind == K::JsxNamespaceName;
    let (name, attribute) = if namespaced {
        (parent.node, grand)
    } else {
        (node, Some(parent))
    };
    attribute.is_some_and(|attribute| {
        attribute.kind == K::JsxAttribute && attribute.node.child(0) == Some(name)
    })
}

/// `_is_member_name`: the name of a method, a field or an attribute, which is not a reference.
pub(crate) fn is_member_name(
    cx: &Cx,
    node: Node,
    relatives: (Option<&Entry>, Option<&Entry>),
) -> bool {
    let (Some(parent), grand) = relatives else {
        return false;
    };
    if jsx_attribute_name(node, parent, grand) {
        return true;
    }
    if parent.kind == K::MemberExpression {
        return false;
    }
    matches!(
        parent.kind,
        K::MethodDefinition | K::MethodSignature | K::PublicFieldDefinition | K::PropertySignature
    ) && cx.field(parent.node, F::Name) == Some(node)
}

/// `_class_member`, for a node whose parent and grandparent are given.
pub(crate) fn class_member(relatives: (Option<&Entry>, Option<&Entry>)) -> bool {
    let (Some(parent), Some(grand)) = relatives else {
        return false;
    };
    matches!(parent.kind, K::ClassBody | K::InterfaceBody)
        && matches!(grand.kind, K::ClassDeclaration | K::InterfaceDeclaration)
}

/// `_subscript_receiver`: the node is the object of a subscript.
pub(crate) fn subscript_receiver(cx: &Cx, node: Node, parent: Option<&Entry>) -> bool {
    parent.is_some_and(|parent| {
        parent.kind == K::SubscriptExpression && cx.field(parent.node, F::Object) == Some(node)
    })
}

/// The entry that is `count`-th from the root: `nth(stack, stack.len())` is the parent of the node
/// that the walk enters.
fn nth<'a, 't>(stack: &'a [Entry<'t>], count: usize) -> Option<&'a Entry<'t>> {
    count.checked_sub(1).and_then(|at| stack.get(at))
}

/// `_script_wrapper` is not `None` for a function expression or an arrow function: a direct,
/// synchronous call that stands alone at the top of a script and passes `window` or `globalThis`
/// for each of its required parameters. `stack` ends with the parent of `node`.
pub(crate) fn is_wrapper(cx: &Cx, node: Node, stack: &[Entry]) -> bool {
    if cx.has_child(node, K::Async) {
        return false;
    }
    let mut callee = node;
    let mut count = stack.len();
    while let Some(entry) = nth(stack, count).filter(|e| e.kind == K::ParenthesizedExpression) {
        callee = entry.node;
        count -= 1;
    }
    let Some(call) = nth(stack, count).filter(|call| {
        call.kind == K::CallExpression && cx.field(call.node, F::Function) == Some(callee)
    }) else {
        return false;
    };
    let mut above = count.saturating_sub(1);
    if nth(stack, above).is_some_and(|entry| entry.kind == K::VariableDeclarator) {
        above = above.saturating_sub(1);
    }
    let at_top = nth(stack, above).is_some_and(|entry| {
        matches!(
            entry.kind,
            K::ExpressionStatement | K::VariableDeclaration | K::LexicalDeclaration
        )
    }) && nth(stack, above.saturating_sub(1))
        .is_some_and(|entry| entry.kind == K::Program);
    at_top && passes_roots(cx, node, call.node)
}

/// The parameters and the arguments pair up: each argument is `window` or `globalThis`, and each
/// parameter is a required parameter with a plain name.
fn passes_roots(cx: &Cx, function: Node, call: Node) -> bool {
    let parameters = cx
        .field(function, F::Parameters)
        .map(named_children)
        .unwrap_or_default();
    let arguments = cx
        .field(call, F::Arguments)
        .map(named_children)
        .unwrap_or_default();
    parameters.len() == arguments.len()
        && parameters
            .iter()
            .zip(&arguments)
            .all(|(parameter, argument)| {
                cx.k(*argument) == K::Identifier
                    && is_script_root(
                        cx.source
                            .data
                            .get(argument.start_byte()..argument.end_byte())
                            .unwrap_or(&[]),
                    )
                    && cx.k(*parameter) == K::RequiredParameter
                    && cx
                        .field(*parameter, F::Pattern)
                        .is_some_and(|pattern| cx.k(pattern) == K::Identifier)
            })
}

/// `_written_string`: the literal that a comparison writes, through the wrappers that keep the
/// value. A node inside a repair is no fact; a caller that skips repaired nodes has none below it.
pub(crate) fn written_string<'t>(cx: &Cx, start: Option<Node<'t>>) -> Option<Node<'t>> {
    let mut node = start?;
    while matches!(
        cx.k(node),
        K::ParenthesizedExpression
            | K::AsExpression
            | K::SatisfiesExpression
            | K::NonNullExpression
    ) {
        if node.has_error() {
            return None;
        }
        let kids: Vec<Node> = named_children(node)
            .into_iter()
            .filter(|item| cx.k(*item) != K::Comment)
            .collect();
        // `as const` has no type child; the other forms of `as` and `satisfies` carry a type, and
        // only the first expression child can give a value.
        let counted = match cx.k(node) {
            K::AsExpression => kids.len() == 1 || kids.len() == 2,
            K::SatisfiesExpression => kids.len() == 2,
            _ => kids.len() == 1,
        };
        node = *kids.first().filter(|_| counted)?;
    }
    if node.has_error() {
        return None;
    }
    match cx.k(node) {
        K::String => Some(node),
        K::TemplateString => named_children(node)
            .into_iter()
            .all(|item| matches!(cx.k(item), K::StringFragment | K::EscapeSequence))
            .then_some(node),
        _ => None,
    }
}

/// `augmentations.compares`: the binary expression is `==`, `!=`, `===` or `!==`. A member that it
/// compares is read and does not leave the script (#1007).
fn compares(cx: &Cx, node: Node) -> bool {
    [K::Equal, K::NotEqual, K::StrictEqual, K::StrictNotEqual]
        .into_iter()
        .any(|kind| cx.has_child(node, kind))
}

/// `_script_escape`: whether a reference to a name lets the value leave the script. `callee_wraps`
/// tells whether the call that holds the arguments is a wrapper of a script.
pub(crate) fn script_escape(
    cx: &Cx,
    node: Node,
    relatives: (Option<&Entry>, Option<&Entry>),
) -> bool {
    let (parent, grand) = relatives;
    let member = parent.filter(|parent| {
        parent.kind == K::MemberExpression && cx.field(parent.node, F::Property) == Some(node)
    });
    let (target, above) = match member {
        Some(parent) => (parent.node, grand),
        None => (node, parent),
    };
    let Some(above) = above else {
        return true;
    };
    if above.kind == K::Pair && cx.field(above.node, F::Key) == Some(target) {
        return false;
    }
    let operand = |kind: K| cx.has_child(above.node, kind);
    if above.kind == K::Arguments && above.wrapped_call {
        return false;
    }
    if matches!(above.kind, K::MemberExpression | K::SubscriptExpression)
        && cx.field(above.node, F::Object) == Some(target)
        || above.kind == K::UnaryExpression && operand(K::Typeof)
        || member.is_some() && above.kind == K::BinaryExpression && compares(cx, above.node)
    {
        return false;
    }
    let assigned = matches!(
        above.kind,
        K::AssignmentExpression | K::AugmentedAssignmentExpression
    ) && cx.field(above.node, F::Left) == Some(target);
    !(assigned
        || above.kind == K::UpdateExpression
        || above.kind == K::UnaryExpression && operand(K::Delete))
}

#[cfg(test)]
#[path = "site_syntax_tests.rs"]
mod tests;
