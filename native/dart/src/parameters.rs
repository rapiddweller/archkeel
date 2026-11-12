// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The parameters, the return types and the annotations of `analyzer/dart/parse.py`.

use tree_sitter::Node;

use crate::pytext::{has_ascii_word, is_space, lstrip, strip};
use crate::syntax::{Parameter, ParameterKind};
use crate::tree::{
    children, first_in_walk, first_named_of, named, named_all, named_children, Source, Work,
};

/// The words that `_annotation_before` removes from the start of an annotation.
const LEADING_WORDS: [&str; 8] = [
    "static",
    "const",
    "final",
    "late",
    "external",
    "covariant",
    "required",
    "var",
];

/// `_annotation_before`: the text between `node` and `name` without the leading modifiers.
pub(crate) fn annotation_before(
    node: Node<'_>,
    name: Node<'_>,
    source: &Source<'_>,
) -> Option<String> {
    let value = source.decode(node.start_byte(), name.start_byte());
    let mut rest = value.trim_start_matches(is_space);
    'words: loop {
        for word in LEADING_WORDS {
            let Some(tail) = rest.strip_prefix(word) else {
                continue;
            };
            let after = tail.trim_start_matches(is_space);
            if after.len() < tail.len() {
                rest = after;
                continue 'words;
            }
        }
        break;
    }
    let value = strip(rest);
    (!value.is_empty()).then(|| value.to_owned())
}

/// `_return_type`: the annotation before the name, without a trailing `get` or `set`.
pub(crate) fn return_type(
    signature: Node<'_>,
    name: Option<Node<'_>>,
    source: &Source<'_>,
) -> Option<String> {
    let annotation = annotation_before(signature, name?, source)?;
    let annotation = without_accessor(&annotation);
    (annotation != "set").then(|| annotation.to_owned())
}

/// `re.sub(r"\s+(?:get|set)\s*$", "", text)` for a stripped text.
fn without_accessor(text: &str) -> &str {
    let Some(head) = text
        .strip_suffix("get")
        .or_else(|| text.strip_suffix("set"))
    else {
        return text;
    };
    let kept = head.trim_end_matches(is_space);
    if kept.len() < head.len() {
        kept
    } else {
        text
    }
}

/// `_parameter_list`.
pub(crate) fn parameter_list(node: Node<'_>) -> Option<Node<'_>> {
    named(node, "parameters").or_else(|| named(node, "formal_parameter_list"))
}

/// `_parameters`: the formal parameters of a list, with the named and the optional groups.
pub(crate) fn parameters<'t>(
    node: Option<Node<'t>>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> Vec<Parameter> {
    let Some(node) = node else {
        return Vec::new();
    };
    let mut result = Vec::new();
    for group in work.family(node).nodes.iter().copied() {
        match group.kind() {
            "formal_parameter" => {
                let kind = ParameterKind::Positional;
                result.push(parameter_in(group, kind, Some(node), source, work));
            }
            "optional_formal_parameters" => {
                let kind = if opens_with(group, '{', source) {
                    ParameterKind::Named
                } else {
                    ParameterKind::Positional
                };
                result.extend(
                    named_all(Some(group), "formal_parameter")
                        .into_iter()
                        .map(|item| parameter_in(item, kind, Some(group), source, work)),
                );
            }
            _ => {}
        }
    }
    result
}

/// `_lexeme(source.text(node).lstrip()[:1]) is <bracket>`. The text is read in growing parts until
/// it holds two characters after the white space, so a long group is not copied for its first
/// character: the first of two characters is never the cut end of a character.
fn opens_with(node: Node<'_>, bracket: char, source: &Source<'_>) -> bool {
    let mut end = node.start_byte().saturating_add(64);
    loop {
        let part = source.decode(node.start_byte(), end.min(node.end_byte()));
        let head = lstrip(&part);
        if head.chars().nth(1).is_some() || end >= node.end_byte() {
            return head.starts_with(bracket);
        }
        end = end.saturating_add(end.saturating_sub(node.start_byte()).saturating_mul(3));
    }
}

/// `_parameter` of a node that has its parent in the walk.
pub(crate) fn parameter<'t>(
    node: Node<'t>,
    kind: ParameterKind,
    source: &Source<'_>,
    work: &Work<'t>,
) -> Parameter {
    parameter_in(node, kind, node.parent(), source, work)
}

/// `_parameter`: `parent` is the list or the group that holds `node`.
pub(crate) fn parameter_in<'t>(
    node: Node<'t>,
    kind: ParameterKind,
    parent: Option<Node<'t>>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> Parameter {
    let field = first_in_walk(node, &["constructor_param", "field_formal_parameter"]);
    let super_formal =
        first_in_walk(node, &["super_formal_parameter", "super_parameter"]).is_some();
    let name_node = named_children(node)
        .into_iter()
        .rev()
        .find(|item| matches!(item.kind(), "identifier" | "type_identifier"))
        .or_else(|| first_in_walk(node, &["identifier"]));
    let name = source.text(name_node.unwrap_or(node));
    let mut annotation = match name_node {
        Some(name_node) if field.is_none() && !super_formal => {
            annotation_before(node, name_node, source)
        }
        _ => None,
    };
    if let (Some(text), Some(nested)) = (&annotation, parameter_list(node)) {
        let list = source.text(nested);
        work.charge(list.len());
        annotation = Some(format!("{text} Function{list}"));
    }
    let mut default = parameter_default(node, parent, source, work);
    let before = parent.map_or(&b""[..], |parent| {
        source
            .data
            .get(parent.start_byte()..node.start_byte())
            .unwrap_or(b"")
    });
    let last = before.rsplit(|b| *b == b',').next().unwrap_or(before);
    let required = has_ascii_word(last, b"required");
    let mut optional = kind == ParameterKind::Named && !required;
    if let Some(parent) = parent.filter(|item| item.kind() == "optional_formal_parameters") {
        optional = opens_with(parent, '[', source) || optional;
    }
    let nullable_or_dynamic = annotation
        .as_deref()
        .is_none_or(|text| text.ends_with('?') || text == "dynamic");
    if default.is_none() && optional && nullable_or_dynamic {
        default = Some("null".to_owned());
    }
    Parameter {
        name,
        annotation,
        kind,
        default,
        default_known: !super_formal,
        span: source.span(node),
        field_formal: field.is_some(),
        super_formal,
        optional,
        required,
    }
}

/// `_parameter_default`.
fn parameter_default<'t>(
    node: Node<'t>,
    parent: Option<Node<'t>>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> Option<String> {
    let all = children(node);
    let marked = all
        .iter()
        .take(all.len().saturating_sub(1))
        .position(|child| matches!(child.kind(), "=" | ":"));
    if let Some(next) = marked.and_then(|at| all.get(at.saturating_add(1))) {
        return Some(source.text(*next));
    }
    if let Some(family) = parent.map(|parent| work.family(parent)) {
        if let Some(following) = family.after(node).and_then(<[Node<'t>]>::first) {
            let between = source
                .data
                .get(node.end_byte()..following.start_byte())
                .unwrap_or(b"");
            if between.contains(&b'=') {
                return Some(source.text(*following));
            }
        }
    }
    let candidate = first_named_of(node, &["default_formal_parameter"])?;
    named_children(candidate)
        .first()
        .map(|item| source.text(*item))
}
