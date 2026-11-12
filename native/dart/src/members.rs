// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The class members and the variables of `analyzer/dart/parse.py`: constructors, methods,
//! accessors, operators, fields and top-level variables.

use tree_sitter::Node;

use crate::parameters::{annotation_before, parameter_list, parameters, return_type};
use crate::pytext::{has_word, strip};
use crate::syntax::{Definition, DefinitionKind, Member, MemberKind};
use crate::tree::{
    children, first_identifier, first_named_of, named, named_children, prefix, Gap, Source, Work,
};

/// The gap of the definition walks: they count their work as the site walks do (AD-376).
pub(crate) const WORK_GAP: Gap = Gap("the work passes the limit of the definition walks");

const CONSTRUCTORS: [&str; 3] = [
    "constructor_signature",
    "constant_constructor_signature",
    "redirecting_factory_constructor_signature",
];

/// `_member_declaration`: a constructor, a method or the fields of one declaration. `parent` is
/// the class body that holds `node`.
pub(crate) fn member_declaration<'t>(
    node: Node<'t>,
    parent: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> Result<Vec<Member>, Gap> {
    if let Some(constructor) = first_named_of(node, &CONSTRUCTORS) {
        let member = constructor_member(node, constructor, parent, source, work);
        return Ok(vec![member]);
    }
    let signatures = ["function_signature", "getter_signature", "setter_signature"];
    if first_named_of(node, &signatures).is_some() {
        return Ok(vec![member_method(node, None, parent, source, work)]);
    }
    field_members(node, &variable_items(node), source, work)
}

fn constructor_member<'t>(
    node: Node<'t>,
    constructor: Node<'t>,
    parent: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> Member {
    let joined = identifiers(constructor, source).join(".");
    let name = if joined.is_empty() {
        first_identifier(Some(constructor), source).unwrap_or_default()
    } else {
        joined
    };
    let mut member = Member::new(
        name,
        MemberKind::Constructor,
        member_span(node, None, parent, work, source),
    );
    member.parameters = parameters(parameter_list(constructor), source, work);
    member.constructor_initializers = named(node, "initializers")
        .map(|initializers| {
            named_children(initializers)
                .into_iter()
                .map(|item| source.text(item))
                .collect()
        })
        .unwrap_or_default();
    member.redirect = redirect(node, source);
    member.factory = constructor.kind() == "redirecting_factory_constructor_signature";
    member.constant = constructor.kind() == "constant_constructor_signature"
        || children(constructor)
            .iter()
            .any(|child| child.kind() == "const_builtin");
    member
}

/// The texts of the named `identifier` children of a node.
fn identifiers(node: Node<'_>, source: &Source<'_>) -> Vec<String> {
    named_children(node)
        .into_iter()
        .filter(|item| item.kind() == "identifier")
        .map(|item| source.text(item))
        .collect()
}

/// `_member_method`: a method, an accessor, an operator or a constructor signature.
pub(crate) fn member_method<'t>(
    node: Node<'t>,
    body: Option<Node<'t>>,
    parent: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> Member {
    let inner = named_children(node).first().copied().unwrap_or(node);
    let signature = named(inner, "function_signature").unwrap_or(inner);
    let factory = inner.kind() == "factory_constructor_signature";
    let constructor = factory || CONSTRUCTORS.contains(&inner.kind());
    let name_node = named(signature, "name").or_else(|| named(inner, "name"));
    let name = if constructor {
        identifiers(inner, source).join(".")
    } else {
        name_node.map_or_else(|| operator_name(inner, source), |item| source.text(item))
    };
    let kind = match inner.kind() {
        _ if constructor => MemberKind::Constructor,
        "getter_signature" => MemberKind::Getter,
        "setter_signature" => MemberKind::Setter,
        "operator_signature" => MemberKind::Operator,
        _ => MemberKind::Method,
    };
    let mut modifiers = source.decode(node.start_byte(), signature.start_byte());
    modifiers.push_str(&prefix(node, parent, source, work));
    let span = member_span(node, body, parent, work, source);
    let mut member = Member::new(name, kind, span);
    member.return_type = return_type(signature, name_node, source);
    member.r#static = has_word(&modifiers, "static");
    member.r#abstract = body.is_none() || has_word(&modifiers, "abstract");
    member.parameters = parameters(parameter_list(signature), source, work);
    member.factory = factory;
    member.redirect = redirect(node, source);
    member
}

/// `_member_span`: from the first annotation or doc comment before the node to its body.
fn member_span<'t>(
    node: Node<'t>,
    body: Option<Node<'t>>,
    parent: Node<'t>,
    work: &Work<'t>,
    source: &Source<'_>,
) -> crate::syntax::Span {
    let mut start = node.start_byte();
    let family = work.family(parent);
    if let Some(mut at) = family.position(node) {
        while let Some(previous) = at
            .checked_sub(1)
            .and_then(|before| family.nodes.get(before))
        {
            work.charge(1);
            if !matches!(
                previous.kind(),
                "annotation" | "documentation_comment" | "metadata"
            ) {
                break;
            }
            at = at.saturating_sub(1);
            start = previous.start_byte();
        }
    }
    let end = body.map_or(node.end_byte(), |body| body.end_byte());
    source.span_bytes(start, end)
}

/// `_redirect`: the target of a redirecting constructor.
fn redirect(node: Node<'_>, source: &Source<'_>) -> Option<String> {
    let kinds = ["redirection", "redirecting_factory_constructor_signature"];
    let found = first_named_of(node, &kinds)?;
    let raw = source.text(found);
    let marker = if found.kind() == kinds[1] { '=' } else { ':' };
    Some(match raw.split_once(marker) {
        Some((_, rest)) => strip(rest).to_owned(),
        None => raw,
    })
}

/// `_operator_name`.
fn operator_name(node: Node<'_>, source: &Source<'_>) -> String {
    let operator = first_named_of(node, &["binary_operator", "unary_operator"]).or_else(|| {
        children(node)
            .into_iter()
            .find(|child| matches!(child.kind(), "[]" | "[]="))
    });
    operator.map_or_else(
        || "operator".to_owned(),
        |item| format!("operator{}", source.text(item)),
    )
}

/// The kinds that `_variable_list_node` accepts.
const VARIABLE_LISTS: [&str; 4] = [
    "initialized_identifier_list",
    "static_final_declaration_list",
    "initialized_variable_definition",
    "initialized_identifier",
];

/// `_variables` without the kind: the items of the declaration list of `node`.
fn variable_items(node: Node<'_>) -> Vec<Node<'_>> {
    let list = if VARIABLE_LISTS.contains(&node.kind()) {
        Some(node)
    } else {
        first_named_of(node, &VARIABLE_LISTS)
    };
    match list {
        None => Vec::new(),
        Some(list) if VARIABLE_LISTS[..2].contains(&list.kind()) => named_children(list),
        Some(list) => vec![list],
    }
}

/// The first named `identifier` child: the name of a variable item.
fn item_name(item: Node<'_>) -> Option<Node<'_>> {
    first_named_of(item, &["identifier"])
}

/// `_field_members`.
fn field_members<'t>(
    node: Node<'t>,
    items: &[Node<'t>],
    source: &Source<'_>,
    work: &Work<'t>,
) -> Result<Vec<Member>, Gap> {
    let declaration = source.text(node);
    let words = Words::of(&declaration);
    let mut members = Vec::new();
    for item in items {
        work.charge(1);
        let Some(name_node) = item_name(*item) else {
            continue;
        };
        // The annotation of each item starts at the declaration: a long list copies its head again
        // for each item. Python does the same, so the copy is counted, and it stops at the limit.
        work.charge(name_node.start_byte().saturating_sub(node.start_byte()));
        work.charge(source.take_decoded());
        work.within(WORK_GAP)?;
        let value = initializer(*item, source);
        let mut member = Member::new(
            source.text(name_node),
            MemberKind::Field,
            source.span(*item),
        );
        member.annotation = annotation_before(node, name_node, source);
        member.r#static = words.r#static;
        member.literal.clone_from(&value);
        member.initializer = value;
        member.constant = words.constant;
        member.r#final = words.r#final;
        member.late = words.late;
        members.push(member);
    }
    Ok(members)
}

/// The modifier words of a declaration text, read once for all its items.
struct Words {
    r#static: bool,
    constant: bool,
    r#final: bool,
    late: bool,
}

impl Words {
    fn of(declaration: &str) -> Self {
        Self {
            r#static: has_word(declaration, "static"),
            constant: has_word(declaration, "const"),
            r#final: has_word(declaration, "final"),
            late: has_word(declaration, "late"),
        }
    }
}

/// `_variables` for top-level variables.
pub(crate) fn top_level_variables<'t>(
    node: Node<'t>,
    parent: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> Result<Vec<Definition>, Gap> {
    let declaration = declaration_text(node, parent, source, work);
    let words = Words::of(&declaration);
    let mut definitions = Vec::new();
    for item in variable_items(node) {
        work.charge(1);
        let Some(name_node) = item_name(item) else {
            continue;
        };
        work.charge(name_node.start_byte().saturating_sub(node.start_byte()));
        work.charge(source.take_decoded());
        work.within(WORK_GAP)?;
        let value = initializer(item, source);
        let mut definition = Definition::new(
            source.text(name_node),
            DefinitionKind::Variable,
            source.span(item),
        );
        definition.return_type = annotation_before(node, name_node, source);
        definition.literal.clone_from(&value);
        definition.initializer = value;
        definition.constant = words.constant;
        definition.r#final = words.r#final;
        definition.late = words.late;
        definitions.push(definition);
    }
    Ok(definitions)
}

/// `_initializer`: the node after the first `=` child.
fn initializer(node: Node<'_>, source: &Source<'_>) -> Option<String> {
    let all = children(node);
    let equal = all.iter().position(|child| child.kind() == "=")?;
    all.get(equal.saturating_add(1))
        .map(|item| source.text(*item))
}

/// `_declaration_text`: the modifier siblings before a declaration, or its own text.
fn declaration_text<'t>(
    node: Node<'t>,
    parent: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
) -> String {
    let family = work.family(parent);
    let siblings = &family.nodes;
    // Python slices `siblings[:-1]` when the node is not found; a named node is always found.
    let before = match family.position(node) {
        Some(at) => siblings.get(..at).unwrap_or(&[]),
        None => siblings
            .get(..siblings.len().saturating_sub(1))
            .unwrap_or(&[]),
    };
    let mut modifiers = Vec::new();
    for sibling in before.iter().rev() {
        work.charge(1);
        match sibling.kind() {
            "const_builtin" | "final_builtin" | "late_builtin" | "static_builtin" => {
                modifiers.push(source.text(*sibling));
            }
            "type_identifier" | "type_name" | "generic_type" | "nullable_type" => {}
            _ => break,
        }
    }
    modifiers.reverse();
    let joined = modifiers.join(" ");
    if joined.is_empty() {
        source.text(node)
    } else {
        joined
    }
}
