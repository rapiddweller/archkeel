// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The parts of a definition below its node: members, parameters, bases and decorators.
//!
//! Each function follows the function of the same name in `parse.py`. It reads the children of one
//! node and never walks the tree.

use tree_sitter::Node;

use crate::kinds::{KindMap, F, K};
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

/// Where a node stands: what `node.parent` and `node.prev_named_sibling` give in Python, known from
/// the walk or from the list of the siblings, so that no question climbs the tree. A climb costs the
/// depth of the node, and a nest 8 000 deep would make the walk quadratic.
#[derive(Clone, Copy)]
pub struct Place<'a, 't> {
    pub parent: Option<Node<'t>>,
    pub parent_kind: K,
    pub grand_kind: K,
    /// The decorators and comments that directly precede the node among its named siblings.
    pub before: &'a [Node<'t>],
}

impl Place<'_, '_> {
    /// A node that has no sibling run: a parameter, for example.
    pub const fn apart(parent_kind: K) -> Self {
        Place {
            parent: None,
            parent_kind,
            grand_kind: K::Other,
            before: &[],
        }
    }

    /// `_class_member`: a method or field of the body of a class or interface declaration.
    pub fn class_member(&self) -> bool {
        matches!(self.parent_kind, K::ClassBody | K::InterfaceBody)
            && matches!(
                self.grand_kind,
                K::ClassDeclaration | K::InterfaceDeclaration
            )
    }
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

/// A node with this many children or fewer is read by index, which costs no cursor.
const FEW_CHILDREN: usize = 12;

pub fn named_children(node: Node) -> Vec<Node> {
    if node.child_count() <= FEW_CHILDREN {
        return (0..node.child_count())
            .filter_map(|index| node.child(index))
            .filter(Node::is_named)
            .collect();
    }
    let mut cursor = node.walk();
    node.named_children(&mut cursor).collect()
}

pub fn children(node: Node) -> Vec<Node> {
    if node.child_count() <= FEW_CHILDREN {
        return (0..node.child_count())
            .filter_map(|index| node.child(index))
            .collect();
    }
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

    pub fn field<'t>(&self, node: Node<'t>, field: F) -> Option<Node<'t>> {
        self.kinds.field(node, field)
    }

    /// Whether a child of `node` has the kind `kind`.
    pub fn has_child(&self, node: Node, kind: K) -> bool {
        children(node).iter().any(|child| self.k(*child) == kind)
    }

    /// `_modifiers`.
    pub fn modifiers(&self, node: Node) -> Modifiers {
        self.modifiers_in(&children(node))
    }

    /// `_modifiers` for the children of a node that the caller already has.
    pub fn modifiers_in(&self, kids: &[Node]) -> Modifiers {
        let mut bits = 0;
        for child in kids.iter().copied() {
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
        self.visibility_in(node, &children(node))
    }

    /// `_visibility` for the children of a node that the caller already has.
    pub fn visibility_in(&self, node: Node, kids: &[Node]) -> Option<Visibility> {
        if kids
            .iter()
            .any(|child| self.k(*child) == K::PrivatePropertyIdentifier)
        {
            return Some(Visibility::Private);
        }
        if let Some(name) = self.field(node, F::Name) {
            if self.k(name) == K::PrivatePropertyIdentifier {
                return Some(Visibility::Private);
            }
        }
        let bits = self.modifiers_in(kids).0;
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
                .field(item, F::Pattern)
                .or_else(|| self.field(item, F::Name))
                .or_else(|| named.first().copied());
            let mut name = pattern.map_or_else(String::new, |pattern| self.text(pattern));
            let rest = self.k(item) == K::RestParameter
                || pattern.is_some_and(|pattern| self.k(pattern) == K::RestPattern);
            if rest {
                name = name.strip_prefix("...").unwrap_or(&name).to_owned();
            }
            result.push(Parameter {
                name,
                annotation: self.type_text(self.field(item, F::Type)),
                optional: self.k(item) == K::OptionalParameter || self.has_child(item, K::Question),
                rest,
                default: self.field(item, F::Value).map(|value| self.text(value)),
            });
        }
        result
    }

    /// `_decorators`: the attached decorators and the sibling decorators of a class member.
    /// `_decorators`, from the children of the node (the caller has them).
    pub fn decorators_in<'t>(
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
    pub fn decorated_member(&self, candidate: Node, place: &Place) -> bool {
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

    /// `_signature_complete`.
    pub fn signature_complete(&self, node: Node) -> bool {
        let Some(parameters) = self.field(node, F::Parameters) else {
            return true;
        };
        named_children(parameters).into_iter().all(|item| {
            self.k(item) == K::RequiredParameter
                && self
                    .field(item, F::Pattern)
                    .or_else(|| self.field(item, F::Name))
                    .is_some_and(|pattern| self.k(pattern) == K::Identifier)
                && self.field(item, F::Value).is_none()
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
                    let candidate = self.field(named, F::Name).unwrap_or(named);
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
