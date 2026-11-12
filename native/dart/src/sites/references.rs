// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `_reference_sites` of `analyzer/dart/parse.py` and its tests of an identifier: the type
//! sites, the typed receivers, the member references and the plain references. The ancestors
//! of a node come from the walk, root first, in place of `_ancestors`.

use std::collections::HashSet;

use tree_sitter::Node;

use super::calls::{assignment_use, member_parts, member_reference, ASSIGNMENTS};
use crate::syntax::{Context, Site, SiteKind, SiteUse};
use crate::tree::{named, Source, Work};

const TYPES: [&str; 3] = ["type_identifier", "generic_type", "function_type"];
const TYPE_PARAMETERS: [&str; 2] = ["type_parameters", "type_parameter"];
const DECLARING_PARENTS: [&str; 6] = [
    "type_identifier",
    "enum_constant",
    "library_name",
    "initialized_identifier",
    "constructor_param",
    "super_formal_parameter",
];
const TYPE_CONTEXTS: [&str; 11] = [
    "type_identifier",
    "type_annotation",
    "type_parameters",
    "type_parameter",
    "type_alias",
    "function_type",
    "generic_type",
    "nullable_type",
    "superclass",
    "interfaces",
    "mixins",
];
const USE_BOUNDARIES: [&str; 3] = ["function_body", "block", "expression_statement"];
const MEMBER_SELECTOR: &str = "unconditional_assignable_selector";

/// The names that `_reference_sites` reads besides the node.
pub(crate) struct Names<'a> {
    pub(crate) receivers: &'a HashSet<String>,
    pub(crate) prefixes: &'a HashSet<String>,
}

/// `_reference_sites`. `ancestors` are the ancestors of `node`, root first.
pub(crate) fn reference_sites<'t>(
    node: Node<'t>,
    ancestors: &[Node<'t>],
    source: &Source<'_>,
    work: &Work<'t>,
    context: &Context,
    names: &Names<'_>,
) -> Option<Site> {
    let parent = ancestors.last().copied();
    if TYPES.contains(&node.kind()) {
        if parent.is_none_or(|parent| TYPE_PARAMETERS.contains(&parent.kind())) {
            return None;
        }
        let (name, receiver, computed) = member_parts(Some(node), source);
        let kind = type_site_kind(ancestors, work);
        let mut site = Site::new(kind, source.text(node), source.span(node), context);
        site.name = name;
        site.receiver = receiver;
        site.r#use = SiteUse::Type;
        site.computed = computed;
        return Some(site);
    }
    let parent = parent?;
    if node.kind() != "identifier" || is_declaration_name(node, parent) {
        return None;
    }
    let family = work.family(parent);
    // `position >= 0 and any(...)` of Python: the selectors after the node, read once.
    let later = family
        .position(node)
        .map(|at| family.later(at.saturating_add(1)));
    if let Some(later) = later.filter(|later| later.member) {
        let name = source.text(node);
        // `_receiver_needs_site`: a later call or index, else a later member access.
        let needs_site = later.call || later.index || later.member;
        if names.receivers.contains(&name) && !names.prefixes.contains(&name) && needs_site {
            let mut site = Site::new(
                SiteKind::Reference,
                name.clone(),
                source.span(node),
                context,
            );
            site.name = Some(name);
            return Some(site);
        }
        return None;
    }
    if parent.kind() == MEMBER_SELECTOR {
        if is_call_selector(ancestors, work) {
            return None;
        }
        let member = member_reference(node, ancestors, source, work);
        let mut site = Site::new(SiteKind::Reference, member.expression, member.span, context);
        site.name = Some(member.name);
        site.receiver = member.receiver;
        site.r#use = reference_use(node, ancestors, source, work);
        site.computed = member.computed;
        return Some(site);
    }
    work.charge(ancestors.len());
    let in_type = ancestors
        .iter()
        .any(|item| TYPE_CONTEXTS.contains(&item.kind()));
    let callee = later.is_some_and(|later| later.call);
    if in_type || callee {
        return None;
    }
    let mut site = Site::new(
        SiteKind::Reference,
        source.text(node),
        source.span(node),
        context,
    );
    site.name = Some(source.text(node));
    site.r#use = reference_use(node, ancestors, source, work);
    Some(site)
}

/// `_type_site_kind`: the clause of the nearest class header, else a plain type.
fn type_site_kind<'t>(ancestors: &[Node<'t>], work: &Work<'t>) -> SiteKind {
    for parent in ancestors.iter().rev() {
        work.charge(1);
        match parent.kind() {
            "interfaces" => return SiteKind::Implements,
            "mixins" => return SiteKind::With,
            "superclass" => return SiteKind::Extends,
            "class_body" | "program" => break,
            _ => {}
        }
    }
    SiteKind::Type
}

/// `_is_declaration_name`.
fn is_declaration_name<'t>(node: Node<'t>, parent: Node<'t>) -> bool {
    parent.child_by_field_name("name") == Some(node) || DECLARING_PARENTS.contains(&parent.kind())
}

/// `_is_call_selector`: a later selector of the chain holds the arguments of a call.
fn is_call_selector<'t>(ancestors: &[Node<'t>], work: &Work<'t>) -> bool {
    let [.., chain, selector, _] = ancestors else {
        return false;
    };
    if selector.kind() != "selector" {
        return false;
    }
    let family = work.family(*chain);
    // `position` is -1 when the selector is missing, and `siblings[0:]` is each sibling.
    let next = family
        .position(*selector)
        .map_or(0, |at| at.saturating_add(1));
    family.later(next).call
}

/// `_reference_use`: the use of the left side of the nearest assignment, else a read.
fn reference_use<'t>(
    node: Node<'t>,
    ancestors: &[Node<'t>],
    source: &Source<'_>,
    work: &Work<'t>,
) -> SiteUse {
    for parent in ancestors.iter().rev() {
        work.charge(1);
        if ASSIGNMENTS.contains(&parent.kind()) {
            let left = named(*parent, "left");
            if left.is_some_and(|left| {
                left.start_byte() <= node.start_byte() && node.start_byte() < left.end_byte()
            }) {
                return assignment_use(*parent, source);
            }
            break;
        }
        if USE_BOUNDARIES.contains(&parent.kind()) {
            break;
        }
    }
    SiteUse::Read
}
