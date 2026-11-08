// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The members of a class, interface or enumeration (`_declared_members`, `_members_complete`).

use std::collections::HashSet;

use tree_sitter::Node;

use crate::kinds::K;
use crate::members::{named_children, static_member_name, Cx, Member};
use crate::syntax::Span;

impl Cx<'_> {
    /// `_parameter_properties`: `None` when a parameter property cannot be proven.
    fn parameter_properties<'t>(&self, node: Node<'t>) -> Option<Vec<Node<'t>>> {
        if !matches!(self.k(node), K::MethodDefinition | K::MethodSignature) {
            return Some(Vec::new());
        }
        let properties: Vec<Node> = self
            .field(node, "parameters")
            .map(|parameters| {
                named_children(parameters)
                    .into_iter()
                    .filter(|item| self.modifiers(*item).is_property())
                    .collect()
            })
            .unwrap_or_default();
        if !properties.is_empty()
            && (!self.supported_constructor(node) || self.field(node, "body").is_none())
        {
            return None;
        }
        for item in &properties {
            let pattern = self
                .field(*item, "pattern")
                .or_else(|| self.field(*item, "name"));
            let proven = !item.has_error()
                && matches!(self.k(*item), K::RequiredParameter | K::OptionalParameter)
                && pattern.is_some_and(|pattern| {
                    self.k(pattern) == K::Identifier
                        && static_member_name(&self.text(pattern)).is_some()
                })
                && self.modifiers(*item).access_count() <= 1;
            if !proven {
                return None;
            }
        }
        Some(properties)
    }

    /// `_member`.
    fn member(&self, node: Node) -> Option<Member> {
        let name_node = self
            .field(node, "name")
            .or_else(|| self.field(node, "pattern"))
            .or_else(|| {
                matches!(self.k(node), K::PropertyIdentifier | K::Identifier).then_some(node)
            })?;
        if matches!(self.k(name_node), K::Other | K::ComputedPropertyName) {
            return None;
        }
        let literal = self.field(node, "value").and_then(|value| {
            matches!(
                self.k(value),
                K::String | K::Number | K::True | K::False | K::Null
            )
            .then(|| self.text(value))
        });
        Some(Member {
            name: self.text(name_node),
            span: self.span(name_node),
            annotation: self.type_text(self.field(node, "type")),
            visibility: self.visibility(node),
            is_static: self.modifiers(node).has_static()
                || matches!(
                    self.k(node),
                    K::EnumAssignment | K::PropertyIdentifier | K::Identifier
                ),
            literal,
            decorator_sources: self.decorator_sources(node),
        })
    }

    pub fn decorator_sources(&self, node: Node) -> Vec<(String, Span)> {
        self.decorators(node)
            .into_iter()
            .map(|item| (self.text(item), self.span(item)))
            .collect()
    }

    /// `_declared_members`.
    pub fn declared_members(&self, body: Node, class: bool, enumeration: bool) -> Vec<Member> {
        let mut members = Vec::new();
        let mut properties: Vec<Member> = Vec::new();
        for item in named_children(body) {
            let kind = self.k(item);
            if matches!(
                kind,
                K::PublicFieldDefinition | K::PropertySignature | K::EnumAssignment
            ) || (enumeration && matches!(kind, K::PropertyIdentifier | K::Identifier))
            {
                members.extend(self.member(item));
            }
            if class {
                for parameter in self.parameter_properties(item).unwrap_or_default() {
                    if let Some(mut member) = self.member(parameter) {
                        member.literal = None;
                        member.decorator_sources = Vec::new();
                        properties.push(member);
                    }
                }
            }
        }
        let keys: Vec<Option<String>> = members
            .iter()
            .map(|member| static_member_name(&member.name))
            .collect();
        if keys.iter().any(Option::is_none) {
            return members;
        }
        let mut counts = std::collections::HashMap::<&str, usize>::new();
        for name in keys
            .iter()
            .flatten()
            .map(String::as_str)
            .chain(properties.iter().map(|member| member.name.as_str()))
        {
            *counts.entry(name).or_default() += 1;
        }
        let single: Vec<Member> = properties
            .iter()
            .filter(|member| counts.get(member.name.as_str()) == Some(&1))
            .cloned()
            .collect();
        members.extend(single);
        members
    }

    /// `_members_complete`.
    pub fn members_complete(&self, body: Option<Node>) -> bool {
        let Some(body) = body else {
            return false;
        };
        if body.has_error() {
            return false;
        }
        let mut attributes: HashSet<String> = HashSet::new();
        let mut constructors = 0;
        for child in named_children(body) {
            let kind = self.k(child);
            if kind == K::Decorator && self.decorated_member(child).is_some() {
                continue;
            }
            if !matches!(
                kind,
                K::PublicFieldDefinition
                    | K::PropertySignature
                    | K::MethodDefinition
                    | K::MethodSignature
                    | K::EnumAssignment
                    | K::PropertyIdentifier
                    | K::Identifier
                    | K::Comment
            ) {
                return false;
            }
            if matches!(kind, K::PropertyIdentifier | K::Identifier | K::Comment) {
                continue;
            }
            let Some(name) = self.field(child, "name") else {
                return false;
            };
            if matches!(self.k(name), K::Other | K::ComputedPropertyName) {
                return false;
            }
            if matches!(kind, K::PublicFieldDefinition | K::PropertySignature) {
                let fresh =
                    static_member_name(&self.text(name)).is_some_and(|key| attributes.insert(key));
                if !fresh {
                    return false;
                }
            }
            if matches!(kind, K::MethodDefinition | K::MethodSignature) {
                if !self.valid_unicode_member_name(name) {
                    return false;
                }
                let properties = self.parameter_properties(child);
                let constructor = self.instance_constructor(child);
                constructors += usize::from(constructor);
                if constructors > 1
                    || properties.is_none()
                    || (constructor && !self.supported_constructor(child))
                {
                    return false;
                }
                for parameter in properties.unwrap_or_default() {
                    let pattern = self
                        .field(parameter, "pattern")
                        .or_else(|| self.field(parameter, "name"));
                    let Some(pattern) = pattern else {
                        return false;
                    };
                    if !attributes.insert(self.text(pattern)) {
                        return false;
                    }
                }
            }
        }
        true
    }
}
