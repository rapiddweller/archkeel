// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The parts of a definition below its node: members, parameters, bases and decorators.
//!
//! Each function follows the function of the same name in `parse.py`. It reads the children of one
//! node and never walks the tree.

use tree_sitter::Node;

use crate::kinds::{KindMap, K};
use crate::pytext::is_space;
use crate::syntax::{Source, Span};

/// The grammar and the text of one file: what every reader of a node needs.
#[derive(Clone, Copy)]
pub struct Cx<'a> {
    pub kinds: &'a KindMap,
    pub source: &'a Source<'a>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Visibility {
    Public,
    Protected,
    Private,
}

/// The modifiers of a node as a set of bits.
#[derive(Clone, Copy, Default)]
pub struct Modifiers(u8);

const PUBLIC: u8 = 1;
const PROTECTED: u8 = 2;
const PRIVATE: u8 = 4;
const STATIC: u8 = 8;
const ABSTRACT: u8 = 16;
const READONLY: u8 = 32;

impl Modifiers {
    pub fn has_static(self) -> bool {
        self.0 & STATIC != 0
    }

    pub fn has_abstract(self) -> bool {
        self.0 & ABSTRACT != 0
    }

    /// The count of public, private and protected.
    pub fn access_count(self) -> u32 {
        (self.0 & (PUBLIC | PROTECTED | PRIVATE)).count_ones()
    }

    pub fn is_property(self) -> bool {
        self.0 & (PUBLIC | PRIVATE | PROTECTED | READONLY) != 0
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Parameter {
    pub name: String,
    pub annotation: Option<String>,
    pub optional: bool,
    pub rest: bool,
    pub default: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Member {
    pub name: String,
    pub span: Span,
    pub annotation: Option<String>,
    pub visibility: Option<Visibility>,
    pub is_static: bool,
    pub literal: Option<String>,
    pub decorator_sources: Vec<(String, Span)>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Base {
    pub name: String,
    pub realizes: bool,
    pub span: Span,
}

pub fn named_children(node: Node) -> Vec<Node> {
    let mut cursor = node.walk();
    node.named_children(&mut cursor).collect()
}

pub fn children(node: Node) -> Vec<Node> {
    let mut cursor = node.walk();
    node.children(&mut cursor).collect()
}

/// `re.search(r"\\", text)`.
pub fn has_backslash(text: &str) -> bool {
    text.contains('\\')
}

/// `_static_member_name`: the name without its quotes, or `None` when it holds an escape.
pub fn static_member_name(raw: &str) -> Option<String> {
    if has_backslash(raw) {
        return None;
    }
    if raw.starts_with(['\'', '"']) {
        let chars: Vec<char> = raw.chars().collect();
        return Some(
            chars
                .get(1..chars.len() - 1)
                .unwrap_or(&[])
                .iter()
                .collect(),
        );
    }
    Some(raw.to_owned())
}

impl Cx<'_> {
    pub fn k(&self, node: Node) -> K {
        self.kinds.of(node)
    }

    pub fn text(&self, node: Node) -> String {
        self.source.text(node)
    }

    pub fn span(&self, node: Node) -> Span {
        self.source.span(node, None)
    }

    fn bytes(&self, node: Node) -> &[u8] {
        self.source
            .data
            .get(node.start_byte()..node.end_byte())
            .unwrap_or(&[])
    }

    pub fn field<'t>(&self, node: Node<'t>, name: &str) -> Option<Node<'t>> {
        node.child_by_field_name(name)
    }

    /// Whether a child of `node` has the kind `kind`.
    pub fn has_child(&self, node: Node, kind: K) -> bool {
        children(node).iter().any(|child| self.k(*child) == kind)
    }

    /// `_modifiers`.
    pub fn modifiers(&self, node: Node) -> Modifiers {
        let mut bits = 0;
        for child in children(node) {
            if matches!(
                self.k(child),
                K::AccessibilityModifier
                    | K::Static
                    | K::Abstract
                    | K::Override
                    | K::Readonly
                    | K::Declare
            ) {
                bits |= match self.bytes(child) {
                    b"public" => PUBLIC,
                    b"protected" => PROTECTED,
                    b"private" => PRIVATE,
                    b"static" => STATIC,
                    b"abstract" => ABSTRACT,
                    b"readonly" => READONLY,
                    _ => 0,
                };
            }
        }
        Modifiers(bits)
    }

    /// `_visibility`.
    pub fn visibility(&self, node: Node) -> Option<Visibility> {
        if self.has_child(node, K::PrivatePropertyIdentifier) {
            return Some(Visibility::Private);
        }
        if let Some(name) = self.field(node, "name") {
            if self.k(name) == K::PrivatePropertyIdentifier {
                return Some(Visibility::Private);
            }
        }
        let bits = self.modifiers(node).0;
        [
            (PUBLIC, Visibility::Public),
            (PROTECTED, Visibility::Protected),
            (PRIVATE, Visibility::Private),
        ]
        .into_iter()
        .find(|(bit, _)| bits & bit != 0)
        .map(|(_, value)| value)
    }

    /// `_type`: the text of a type; the colon of an annotation is removed.
    pub fn type_text(&self, node: Option<Node>) -> Option<String> {
        let node = node?;
        let value = self.text(node);
        if self.k(node) == K::TypeAnnotation {
            let rest: String = value.chars().skip(1).collect();
            return Some(rest.trim_matches(is_space).to_owned());
        }
        Some(value)
    }

    /// `_parameters`.
    pub fn parameters(&self, node: Option<Node>) -> Vec<Parameter> {
        let Some(node) = node else {
            return Vec::new();
        };
        let mut result = Vec::new();
        for item in named_children(node) {
            let named = named_children(item);
            let pattern = self
                .field(item, "pattern")
                .or_else(|| self.field(item, "name"))
                .or_else(|| named.first().copied());
            let mut name = pattern.map_or_else(String::new, |pattern| self.text(pattern));
            let rest = self.k(item) == K::RestParameter
                || pattern.is_some_and(|pattern| self.k(pattern) == K::RestPattern);
            if rest {
                name = name.strip_prefix("...").unwrap_or(&name).to_owned();
            }
            result.push(Parameter {
                name,
                annotation: self.type_text(self.field(item, "type")),
                optional: self.k(item) == K::OptionalParameter || self.has_child(item, K::Question),
                rest,
                default: self.field(item, "value").map(|value| self.text(value)),
            });
        }
        result
    }

    /// `_class_member`: a method of a class or interface declaration.
    pub fn class_member(&self, node: Node) -> bool {
        let Some(parent) = node.parent() else {
            return false;
        };
        if !matches!(self.k(parent), K::ClassBody | K::InterfaceBody) {
            return false;
        }
        parent.parent().is_some_and(|owner| {
            matches!(self.k(owner), K::ClassDeclaration | K::InterfaceDeclaration)
        })
    }

    /// `_decorators`: the attached decorators and the sibling decorators of a class member.
    pub fn decorators<'t>(&self, node: Node<'t>) -> Vec<Node<'t>> {
        let mut attached: Vec<Node> = Vec::new();
        if let Some(parent) = node.parent() {
            if self.k(parent) == K::ExportStatement {
                attached.extend(
                    named_children(parent)
                        .into_iter()
                        .filter(|child| self.k(*child) == K::Decorator),
                );
            }
        }
        attached.extend(
            named_children(node)
                .into_iter()
                .filter(|child| self.k(*child) == K::Decorator),
        );
        if !self.class_member(node) {
            return attached;
        }
        let mut preceding = Vec::new();
        let mut previous = node.prev_named_sibling();
        while let Some(item) = previous {
            if !matches!(self.k(item), K::Decorator | K::Comment) {
                break;
            }
            if self.k(item) == K::Decorator && self.decorated_member(item) == Some(node) {
                preceding.push(item);
            }
            previous = item.prev_named_sibling();
        }
        preceding.reverse();
        preceding.extend(attached);
        preceding
    }

    /// `_decorated_member`: a decorator at body level belongs to the next supported member.
    pub fn decorated_member<'t>(&self, node: Node<'t>) -> Option<Node<'t>> {
        let mut candidate = node.next_named_sibling();
        while let Some(item) = candidate {
            if !matches!(self.k(item), K::Decorator | K::Comment) {
                break;
            }
            candidate = item.next_named_sibling();
        }
        let candidate = candidate?;
        if candidate.has_error()
            || !matches!(
                self.k(candidate),
                K::MethodDefinition | K::MethodSignature | K::PublicFieldDefinition
            )
        {
            return None;
        }
        let name = self.field(candidate, "name")?;
        (self.k(name) != K::ComputedPropertyName
            && self.valid_unicode_member_name(name)
            && !self.instance_constructor(candidate))
        .then_some(candidate)
    }

    /// `_signature_complete`.
    pub fn signature_complete(&self, node: Node) -> bool {
        let Some(parameters) = self.field(node, "parameters") else {
            return true;
        };
        named_children(parameters).into_iter().all(|item| {
            self.k(item) == K::RequiredParameter
                && self
                    .field(item, "pattern")
                    .or_else(|| self.field(item, "name"))
                    .is_some_and(|pattern| self.k(pattern) == K::Identifier)
                && self.field(item, "value").is_none()
                && !self.has_child(item, K::Question)
        })
    }

    /// The bases of a class, interface or enumeration: `extends` and `implements` clauses.
    pub fn bases(&self, node: Node) -> Vec<Base> {
        let mut bases = Vec::new();
        for heritage in named_children(node) {
            let clauses = match self.k(heritage) {
                K::ClassHeritage => named_children(heritage),
                K::ExtendsTypeClause => vec![heritage],
                _ => Vec::new(),
            };
            for clause in clauses {
                if !matches!(
                    self.k(clause),
                    K::ExtendsClause | K::ImplementsClause | K::ExtendsTypeClause
                ) {
                    continue;
                }
                for named in named_children(clause) {
                    let candidate = self.field(named, "name").unwrap_or(named);
                    bases.push(Base {
                        name: self.text(candidate),
                        realizes: self.k(clause) == K::ImplementsClause,
                        span: self.span(candidate),
                    });
                }
            }
        }
        bases
    }
}
