// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The decorators of a class member (`_decorators`, `_decorated_member`): the ones attached to
//! it and the run of decorators before it that belong to it.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::members::Place;
use crate::tree::cx::Cx;
use crate::tree::nodes::named_children;

impl Cx<'_> {
    /// `_decorators`: the attached decorators and the sibling decorators of a class member.
    /// `_decorators`, from the children of the node (the caller has them).
    pub(crate) fn decorators_in<'t>(
        &self,
        node: Node<'t>,
        kids: &[Node<'t>],
        place: &Place<'_, 't>,
    ) -> Vec<Node<'t>> {
        let mut attached: Vec<Node> = Vec::new();
        if let Some(parent) = place
            .parent
            .filter(|_| place.parent_kind == K::ExportStatement)
        {
            attached.extend(
                named_children(parent)
                    .into_iter()
                    .filter(|child| self.k(*child) == K::Decorator),
            );
        }
        attached.extend(
            kids.iter()
                .copied()
                .filter(|child| self.k(*child) == K::Decorator && child.is_named()),
        );
        if !place.class_member() || !self.decorated_member(node, place) {
            return attached;
        }
        // Each decorator of the run before the member reaches the member: only comments and
        // decorators lie between them.
        let mut preceding: Vec<Node> = place
            .before
            .iter()
            .copied()
            .filter(|item| self.k(*item) == K::Decorator)
            .collect();
        preceding.extend(attached);
        preceding
    }

    /// `_decorated_member` for the member that follows a run of decorators and comments: whether
    /// a decorator at body level belongs to it.
    pub(crate) fn decorated_member(&self, candidate: Node, place: &Place) -> bool {
        if candidate.has_error()
            || !matches!(
                self.k(candidate),
                K::MethodDefinition | K::MethodSignature | K::PublicFieldDefinition
            )
        {
            return false;
        }
        let Some(name) = self.field(candidate, F::Name) else {
            return false;
        };
        self.k(name) != K::ComputedPropertyName
            && self.valid_unicode_member_name(name)
            && !self.instance_constructor(candidate, place)
    }
}
