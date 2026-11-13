// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The two fixed shapes that a script may match exactly: the namespace argument
//! `__publication || (__publication = {})` and the closed UMD envelope (`_umd_matches`).
//!
//! Python parses each template once with the TSX grammar and compares the tree of a candidate
//! with it, node by node. The templates are parsed once for a grammar here as well.

use tree_sitter::{Language, Node, Parser, Tree};

use crate::kinds::K;
use crate::references::literal;
use crate::tree::cx::Cx;
use crate::tree::nodes::children;

const NAMESPACE: &[u8] = b"__publication || (__publication = {})";
const ENVELOPE: &[u8] =
    b"(function(__factory){if(typeof exports===\"object\"&&typeof module!==\"undefined\")\
{module.exports=__factory()}else if(typeof define===\"function\"&&define.amd)\
{define([],__factory)}else{var __root;if(typeof window!==\"undefined\")\
{__root=window}else if(typeof global!==\"undefined\"){__root=global}\
else if(typeof self!==\"undefined\"){__root=self}else{__root=this}\
__root.__publication=__factory()}})";

/// A parsed template and its text.
struct Template {
    tree: Tree,
    data: Vec<u8>,
}

impl Template {
    fn new(parser: &mut Parser, data: &[u8]) -> Option<Self> {
        let tree = parser.parse(data, None)?;
        Some(Self {
            tree,
            data: data.to_vec(),
        })
    }

    /// `root.named_children[0].named_children[0]`: the expression of the one statement.
    fn expression(&self) -> Option<Node<'_>> {
        self.tree.root_node().named_child(0)?.named_child(0)
    }

    fn text(&self, node: Node) -> &[u8] {
        self.data
            .get(node.start_byte()..node.end_byte())
            .unwrap_or(&[])
    }
}

/// The templates of one grammar.
pub(crate) struct Templates {
    namespace: Option<Template>,
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    envelope: Option<Template>,
}

/// The nodes that the slots of a template capture.
#[derive(Default)]
pub(crate) struct Captures<'t> {
    pub(crate) factory: Option<Node<'t>>,
    pub(crate) root: Option<Node<'t>>,
    pub(crate) publication: Option<Node<'t>>,
}

impl Templates {
    pub(crate) fn new(language: &Language) -> Self {
        let mut parser = Parser::new();
        let namespace = parser
            .set_language(language)
            .ok()
            .and_then(|()| Template::new(&mut parser, NAMESPACE));
        let envelope = Template::new(&mut parser, ENVELOPE);
        Self {
            namespace,
            envelope,
        }
    }

    /// `_umd_matches(wrapper, envelope)`: the nodes that the slots of the closed UMD envelope
    /// capture, when the wrapper is that envelope.
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    pub(crate) fn envelope<'t>(&self, cx: Cx, wrapper: Node<'t>) -> Option<Captures<'t>> {
        let template = self.envelope.as_ref()?;
        let pattern = template.expression()?;
        let mut captures = Captures::default();
        matches(cx, wrapper, pattern, template, &mut captures).then_some(captures)
    }

    /// `_umd_matches(argument, namespace template)`: the name that the argument publishes.
    pub(crate) fn publication(&self, cx: Cx, argument: Node) -> Option<String> {
        let template = self.namespace.as_ref()?;
        let pattern = template.expression()?;
        let mut captures = Captures::default();
        if !matches(cx, argument, pattern, template, &mut captures) {
            return None;
        }
        captures.publication.map(|node| cx.text(node))
    }
}

/// `_umd_matches`: the same kinds, the same words and the same strings, and a captured name that
/// is the same wherever it stands.
fn matches<'t>(
    cx: Cx,
    actual: Node<'t>,
    pattern: Node,
    template: &Template,
    captures: &mut Captures<'t>,
) -> bool {
    let kind = cx.k(pattern);
    if kind != cx.k(actual) {
        return false;
    }
    if matches!(kind, K::Identifier | K::PropertyIdentifier) {
        let slot = match template.text(pattern) {
            b"__factory" => Some(&mut captures.factory),
            b"__root" => Some(&mut captures.root),
            b"__publication" => Some(&mut captures.publication),
            _ => None,
        };
        if let Some(slot) = slot {
            let previous = *slot.get_or_insert(actual);
            return cx.text(previous) == cx.text(actual);
        }
    }
    if kind == K::String {
        return literal(Some(actual), cx.source) == pattern_literal(cx, pattern, template);
    }
    let left: Vec<Node> = children(actual)
        .into_iter()
        .filter(|node| cx.k(*node) != K::Comment)
        .collect();
    let right: Vec<Node> = children(pattern)
        .into_iter()
        .filter(|node| cx.k(*node) != K::Comment)
        .collect();
    if left.is_empty() && right.is_empty() {
        return cx.source.data.get(actual.start_byte()..actual.end_byte())
            == Some(template.text(pattern));
    }
    kind != K::Other
        && left.len() == right.len()
        && left
            .into_iter()
            .zip(right)
            .all(|(child, expected)| matches(cx, child, expected, template, captures))
}

/// `_literal` of a string of a template.
fn pattern_literal(cx: Cx, node: Node, template: &Template) -> Option<String> {
    let text = String::from_utf8_lossy(template.text(node)).into_owned();
    if text.contains('\\')
        || children(node)
            .iter()
            .any(|c| cx.k(*c) == K::TemplateSubstitution)
    {
        return None;
    }
    let mut chars = text.chars();
    chars.next();
    chars.next_back();
    Some(chars.as_str().to_owned())
}
