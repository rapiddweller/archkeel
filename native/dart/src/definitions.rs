// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The top-level definitions of `analyzer/dart/parse.py`: classifiers, functions, accessors and
//! variables, sorted by their start byte.

use tree_sitter::Node;

use crate::members::{member_declaration, member_method, top_level_variables};
use crate::parameters::{parameter_list, parameters, return_type};
use crate::pytext::has_word;
use crate::syntax::{Definition, DefinitionKind, Member, Modifier};
use crate::tree::{
    children, first_named_of, named, named_all, named_children, named_in, prefix, Source,
};

/// `_DECLARATIONS`: the kinds that `_classifier` reads.
const DECLARATIONS: [&str; 7] = [
    "class_definition",
    "mixin_declaration",
    "enum_declaration",
    "extension_declaration",
    "extension_type_declaration",
    "type_alias",
    "function_type_alias",
];

/// `_definitions`.
pub(crate) fn definitions(root: Node<'_>, source: &Source<'_>) -> Vec<Definition> {
    let mut result = Vec::new();
    for node in named_children(root) {
        match node.kind() {
            kind if DECLARATIONS.contains(&kind) => result.push(classifier(node, source)),
            "function_signature" => result.push(function(node, source)),
            "getter_signature" | "setter_signature" => result.push(accessor(node, source)),
            "top_level_variable_declaration" => {
                let declaration = first_named_of(node, &["declaration"]).unwrap_or(node);
                result.extend(top_level_variables(declaration, source));
            }
            "static_final_declaration_list" | "initialized_identifier_list" | "declaration" => {
                result.extend(top_level_variables(node, source));
            }
            _ => {}
        }
    }
    result.sort_by_key(|item| item.span.start_byte);
    result
}

/// `_classifier`.
fn classifier(node: Node<'_>, source: &Source<'_>) -> Definition {
    let name_node =
        named(node, "name").or_else(|| first_named_of(node, &["identifier", "type_identifier"]));
    let name = name_node.map(|item| source.text(item)).unwrap_or_default();
    let kind = classifier_kind(node);
    let mut definition = Definition::new(name, kind, source.span(node));
    relations(node, source, &mut definition);
    let body = named(node, "body").or_else(|| first_named_of(node, &["class_body", "enum_body"]));
    if let Some(body) = body {
        if node.kind() == "enum_declaration" {
            enum_literals(body, source, &mut definition);
        }
        definition.members = members(body, source);
    }
    if kind == DefinitionKind::Typedef {
        definition.alias = alias(node, name_node, source);
    }
    let text = match name_node {
        Some(name_node) => source.decode(node.start_byte(), name_node.start_byte()),
        None => prefix(node, source),
    };
    definition.modifiers = Modifier::ALL
        .into_iter()
        .filter(|(_, word)| has_word(&text, word))
        .map(|(modifier, _)| modifier)
        .collect();
    definition
}

/// The enum literals of `_classifier_members`: the name and the span of each constant.
fn enum_literals(body: Node<'_>, source: &Source<'_>, definition: &mut Definition) {
    let names = named_all(Some(body), "enum_constant")
        .into_iter()
        .filter_map(|constant| named(constant, "name"));
    for name in names {
        definition.enum_members.push(source.text(name));
        definition.enum_member_spans.push(source.span(name));
    }
}

/// `_classifier_kind`.
fn classifier_kind(node: Node<'_>) -> DefinitionKind {
    match node.kind() {
        "class_definition" => {
            if children(node)
                .iter()
                .any(|child| child.kind() == "interface")
            {
                DefinitionKind::Interface
            } else {
                DefinitionKind::Class
            }
        }
        "mixin_declaration" => DefinitionKind::Mixin,
        "enum_declaration" => DefinitionKind::Enum,
        "extension_declaration" => DefinitionKind::Extension,
        "extension_type_declaration" => DefinitionKind::ExtensionType,
        _ => DefinitionKind::Typedef,
    }
}

/// `_classifier_relations`: extends (one at most), with, implements and the type parameters.
fn relations(node: Node<'_>, source: &Source<'_>, definition: &mut Definition) {
    let superclass = named(node, "superclass");
    definition.extends = type_children(superclass, source);
    definition.extends.truncate(1);
    let mixins = named_in(superclass, "mixins").or_else(|| named(node, "mixins"));
    definition.with_types = type_children(mixins, source);
    definition.implements = type_children(named(node, "interfaces"), source);
    definition.type_parameters = named_all(named(node, "type_parameters"), "type_parameter")
        .into_iter()
        .filter_map(|child| named_children(child).first().map(|item| source.text(*item)))
        .collect();
}

/// `_type_children`: each type name, with the type arguments that follow it.
fn type_children(node: Option<Node<'_>>, source: &Source<'_>) -> Vec<String> {
    let Some(node) = node else {
        return Vec::new();
    };
    let all = named_children(node);
    let mut names = Vec::new();
    let mut index = 0usize;
    while let Some(child) = all.get(index) {
        if matches!(
            child.kind(),
            "type_identifier" | "type_name" | "generic_type"
        ) {
            let mut value = source.text(*child);
            if let Some(arguments) = all
                .get(index.saturating_add(1))
                .filter(|item| item.kind() == "type_arguments")
            {
                value.push_str(&source.text(*arguments));
                index = index.saturating_add(1);
            }
            names.push(value);
        }
        index = index.saturating_add(1);
    }
    names
}

/// `_classifier_members` without the enum literals.
fn members(body: Node<'_>, source: &Source<'_>) -> Vec<Member> {
    let all = named_children(body);
    let mut members = Vec::new();
    for (index, child) in all.iter().enumerate() {
        let following = all
            .get(index.saturating_add(1))
            .copied()
            .filter(|item| matches!(item.kind(), "function_body" | "function_expression_body"));
        match child.kind() {
            "declaration" => members.extend(member_declaration(*child, source)),
            "method_signature" => members.push(member_method(*child, following, source)),
            _ => {}
        }
    }
    members
}

/// `_classifier_alias`: the aliased type after the name of a typedef.
fn alias(node: Node<'_>, name_node: Option<Node<'_>>, source: &Source<'_>) -> Option<String> {
    let all = named_children(node);
    let after = name_node
        .and_then(|name| all.iter().position(|child| *child == name))
        .map_or(0, |at| at.saturating_add(1));
    all.get(after..)?
        .iter()
        .find(|child| {
            matches!(
                child.kind(),
                "function_type" | "type_identifier" | "generic_type"
            )
        })
        .map(|child| source.text(*child))
}

/// `_top_level_accessor`.
fn accessor(node: Node<'_>, source: &Source<'_>) -> Definition {
    let name_node = named(node, "name");
    let name = name_node.map(|item| source.text(item)).unwrap_or_default();
    let kind = if node.kind() == "getter_signature" {
        DefinitionKind::Getter
    } else {
        DefinitionKind::Setter
    };
    let mut definition = Definition::new(name, kind, source.span(node));
    definition.return_type = return_type(node, name_node, source);
    definition.parameters = parameters(parameter_list(node), source);
    definition
}

/// `_function`.
fn function(node: Node<'_>, source: &Source<'_>) -> Definition {
    let signature = named(node, "function_signature").unwrap_or(node);
    let name_node = named(signature, "name");
    let name = name_node.map(|item| source.text(item)).unwrap_or_default();
    let mut definition = Definition::new(name, DefinitionKind::Function, source.span(node));
    definition.parameters = parameters(parameter_list(signature), source);
    definition.return_type = return_type(signature, name_node, source);
    definition
}
