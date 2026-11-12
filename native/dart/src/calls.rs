// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The expression sites of `analyzer/dart/parse.py`: `_expression_site`, `_creation`,
//! `_call_site`, `_call_name`, `_member_parts`, `_member_reference` and `_assignment_use`.

use tree_sitter::Node;

use crate::canonical::canonical_range;
use crate::pytext::{is_blank, is_space_byte, rstrip, strip};
use crate::syntax::{Context, Site, SiteKind, SiteUse};
use crate::tree::{named, named_all, named_children, Source, Work};

const CREATIONS: [&str; 2] = ["new_expression", "const_object_expression"];
pub(crate) const ASSIGNMENTS: [&str; 2] =
    ["assignment_expression", "compound_assignment_expression"];
const CREATED_TYPES: [&str; 4] = [
    "type_identifier",
    "type_name",
    "generic_type",
    "qualified_type",
];
const CALL_CHAIN: [&str; 4] = [
    "identifier",
    "type_identifier",
    "selector",
    "assignable_expression",
];
const MEMBER_CHAIN: [&str; 3] = ["identifier", "type_identifier", "selector"];

/// `_expression_site`: a creation, an assignment or a call.
pub(crate) fn expression_site<'t>(
    node: Node<'t>,
    ancestors: &[Node<'t>],
    root: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
    context: &Context,
) -> Option<Site> {
    if CREATIONS.contains(&node.kind()) {
        return Some(creation(node, root, source, work, context));
    }
    if ASSIGNMENTS.contains(&node.kind()) {
        let left = named(node, "left");
        let right = named(node, "right");
        let (name, receiver, computed) = member_parts(left, source);
        let mut site = Site::new(
            SiteKind::Assignment,
            source.text(node),
            source.span(node),
            context,
        );
        site.name = name;
        site.receiver = receiver;
        site.initializer = right.map(|right| source.text(right));
        site.r#use = assignment_use(node, source);
        site.computed = computed;
        return Some(site);
    }
    if node.kind() == "arguments" {
        return call_site(node, ancestors, root, source, work, context);
    }
    None
}

/// `_creation`.
fn creation<'t>(
    node: Node<'t>,
    root: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
    context: &Context,
) -> Site {
    let children = named_children(node);
    work.charge(children.len());
    let type_node = children
        .iter()
        .find(|child| CREATED_TYPES.contains(&child.kind()));
    let arguments = named_all(named(node, "arguments"), "argument");
    let mut site = Site::new(
        SiteKind::Creation,
        source.text(node),
        source.span(node),
        context,
    );
    site.name = type_node.map(|type_node| {
        let mut parts = vec![source.text(*type_node)];
        parts.extend(
            children
                .iter()
                .filter(|child| {
                    child.kind() == "identifier" && child.start_byte() > type_node.end_byte()
                })
                .map(|child| source.text(*child)),
        );
        parts.join(".")
    });
    site.arguments = arguments.iter().map(|item| source.text(*item)).collect();
    site.expression_source = Some(canonical_range(
        root,
        source,
        work,
        node.start_byte(),
        node.end_byte(),
    ));
    site
}

/// The start of the chain before `first` among `siblings`: the earlier siblings of one of
/// `kinds` with only white space between them, as the loops of `_call_site` and
/// `_member_reference` find it. `first` is the index of the first chain element.
fn chain_start<'t>(
    siblings: &[Node<'t>],
    first: usize,
    kinds: &[&str],
    source: &Source<'_>,
    work: &Work<'t>,
) -> usize {
    let mut index = first;
    while let Some(previous) = siblings.get(index) {
        work.charge(1);
        let Some(earlier) = index.checked_sub(1).and_then(|at| siblings.get(at)) else {
            break;
        };
        if !kinds.contains(&earlier.kind()) {
            break;
        }
        let gap = source
            .data
            .get(earlier.end_byte()..previous.start_byte())
            .unwrap_or(b"");
        if !is_blank(gap) {
            break;
        }
        index = index.saturating_sub(1);
    }
    index
}

/// The previous named sibling of `node` and the start of the chain that ends with it.
fn previous_chain<'t>(
    node: Node<'t>,
    parent: Option<Node<'t>>,
    kinds: &[&str],
    source: &Source<'_>,
    work: &Work<'t>,
) -> Option<usize> {
    let family = work.family(parent?);
    let first = family.position(node)?.checked_sub(1)?;
    let at = chain_start(&family.nodes, first, kinds, source, work);
    family.nodes.get(at).map(Node::start_byte)
}

/// `_call_site`: the call of an `arguments` node in a selector.
fn call_site<'t>(
    node: Node<'t>,
    ancestors: &[Node<'t>],
    root: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
    context: &Context,
) -> Option<Site> {
    let [head @ .., selector, parent] = ancestors else {
        return None;
    };
    if parent.kind() != "argument_part" || selector.kind() != "selector" {
        return None;
    }
    let selector = *selector;
    let chain = head.last().copied();
    let start = previous_chain(selector, chain, &CALL_CHAIN, source, work)
        .unwrap_or_else(|| selector.start_byte());
    let end = selector.end_byte();
    let prior = source.decode(start, selector.start_byte());
    let (name, receiver, computed) = call_name(strip(&prior));
    let mut site = Site::new(
        SiteKind::Call,
        source.decode(start, end),
        source.span_bytes(start, end),
        context,
    );
    site.name = name;
    site.receiver = receiver;
    site.arguments = named_all(Some(node), "argument")
        .iter()
        .map(|item| source.text(*item))
        .collect();
    site.computed = computed;
    site.expression_source = Some(canonical_range(root, source, work, start, end));
    Some(site)
}

/// `_call_name`: the name, the receiver and the `[` test of the text before a call.
pub(crate) fn call_name(text: &str) -> (Option<String>, Option<String>, bool) {
    let value = rstrip(text);
    let value = value.strip_suffix('.').unwrap_or(value);
    if let Some((receiver, name)) = value.rsplit_once('.') {
        return (non_empty(name), non_empty(receiver), receiver.contains('['));
    }
    let last = value.rsplit_once(' ').map_or(value, |(_, last)| last);
    (non_empty(last), None, value.contains('['))
}

/// `text or None`.
fn non_empty(text: &str) -> Option<String> {
    (!text.is_empty()).then(|| text.to_owned())
}

/// `_member_parts`: the name, the receiver and the `[` test of a member text.
pub(crate) fn member_parts<'t>(
    node: Option<Node<'t>>,
    source: &Source<'_>,
) -> (Option<String>, Option<String>, bool) {
    let Some(node) = node else {
        return (None, None, false);
    };
    let text = source.text(node);
    if let Some((receiver, name)) = text.rsplit_once('.') {
        return (
            Some(name.to_owned()),
            Some(receiver.to_owned()),
            receiver.contains('['),
        );
    }
    let computed = text.contains('[');
    (Some(text), None, computed)
}

/// `_assignment_use`: a plain `=` writes, each other operator reads and writes.
pub(crate) fn assignment_use<'t>(node: Node<'t>, source: &Source<'_>) -> SiteUse {
    let (Some(left), Some(right)) = (named(node, "left"), named(node, "right")) else {
        return SiteUse::Write;
    };
    let operator = source
        .data
        .get(left.end_byte()..right.start_byte())
        .unwrap_or(b"");
    // `bytes.strip()`: it also removes `\x0b`, which `<[u8]>::trim_ascii` keeps.
    let start = operator
        .iter()
        .position(|b| !is_space_byte(*b))
        .unwrap_or(operator.len());
    let end = operator
        .iter()
        .rposition(|b| !is_space_byte(*b))
        .map_or(start, |at| at.saturating_add(1));
    if operator.get(start..end) == Some(&b"="[..]) {
        SiteUse::Write
    } else {
        SiteUse::ReadWrite
    }
}

/// `_member_reference`: the name, the receiver, the `[` test, the text and the span of the
/// member chain of a selector identifier. `ancestors` are the ancestors of `node`, root first.
pub(crate) struct MemberReference {
    pub(crate) name: String,
    pub(crate) receiver: Option<String>,
    pub(crate) computed: bool,
    pub(crate) expression: String,
    pub(crate) span: crate::syntax::Span,
}

pub(crate) fn member_reference<'t>(
    node: Node<'t>,
    ancestors: &[Node<'t>],
    source: &Source<'_>,
    work: &Work<'t>,
) -> MemberReference {
    let name = source.text(node);
    let (selector, outer) = match ancestors {
        [.., outer, selector] => (*selector, *outer),
        _ => {
            return MemberReference {
                expression: name.clone(),
                name,
                receiver: None,
                computed: false,
                span: source.span(node),
            }
        }
    };
    let chain = ancestors
        .len()
        .checked_sub(3)
        .and_then(|at| ancestors.get(at))
        .copied();
    let previous = previous_chain(outer, chain, &MEMBER_CHAIN, source, work);
    let start = previous.unwrap_or_else(|| outer.start_byte());
    let mut receiver = previous.map(|start| source.decode(start, selector.start_byte()));
    if receiver.is_none() {
        receiver = assigned_receiver(node, ancestors, source, work);
    }
    let end = outer.end_byte();
    MemberReference {
        name,
        computed: receiver.as_deref().unwrap_or("").contains('['),
        receiver,
        expression: source.decode(start, end),
        span: source.span_bytes(start, end),
    }
}

/// The receiver of the left side of the nearest assignment whose left side holds `node`.
fn assigned_receiver<'t>(
    node: Node<'t>,
    ancestors: &[Node<'t>],
    source: &Source<'_>,
    work: &Work<'t>,
) -> Option<String> {
    for ancestor in ancestors.iter().rev() {
        work.charge(1);
        if !ASSIGNMENTS.contains(&ancestor.kind()) {
            continue;
        }
        let left = named(*ancestor, "left");
        if let Some(left) = left.filter(|left| {
            left.start_byte() <= node.start_byte() && node.start_byte() < left.end_byte()
        }) {
            return member_parts(Some(left), source).1;
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::call_name;

    fn owned(
        name: Option<&str>,
        receiver: Option<&str>,
        computed: bool,
    ) -> (Option<String>, Option<String>, bool) {
        (
            name.map(str::to_owned),
            receiver.map(str::to_owned),
            computed,
        )
    }

    #[test]
    fn the_call_name_follows_the_python_rules() {
        assert_eq!(call_name("a.b"), owned(Some("b"), Some("a"), false));
        assert_eq!(call_name("a[0].b."), owned(Some("b"), Some("a[0]"), true));
        assert_eq!(call_name("new  A"), owned(Some("A"), None, false));
        assert_eq!(call_name("a."), owned(Some("a"), None, false));
        assert_eq!(call_name(".b"), owned(Some("b"), None, false));
        assert_eq!(call_name("a.."), owned(None, Some("a"), false));
        assert_eq!(call_name(""), owned(None, None, false));
        assert_eq!(call_name("x[1] "), owned(Some("x[1]"), None, true));
    }
}
