// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that a program outside the scan roots declares (#1546): an assignment to any other
//! name replaces a global. The reader is syntactic: a name that the program declares anywhere
//! counts as declared everywhere in it.

use tree_sitter::Node;

/// The kinds that pass a declared name up to its declaration.
const PATTERNS: [&str; 9] = [
    "object_pattern",
    "array_pattern",
    "pair_pattern",
    "assignment_pattern",
    "object_assignment_pattern",
    "rest_pattern",
    "required_parameter",
    "optional_parameter",
    "formal_parameters",
];

/// The kinds that declare the name below them.
const DECLARERS: [&str; 17] = [
    "variable_declarator",
    "function_declaration",
    "generator_function_declaration",
    "class_declaration",
    "abstract_class_declaration",
    "function_expression",
    "generator_function",
    "class",
    "arrow_function",
    "catch_clause",
    "import_specifier",
    "namespace_import",
    "import_clause",
    "enum_declaration",
    "internal_module",
    "formal_parameters",
    "for_in_statement",
];

/// The identifier is a declared name: a name, a pattern or a parameter of a declaration.
pub(crate) fn declares(node: Node) -> bool {
    let mut at = node;
    while let Some(parent) = at.parent() {
        let kind = Node::kind(&parent);
        if DECLARERS.contains(&kind) {
            let field = |name: &str| {
                parent
                    .child_by_field_name(name)
                    .is_some_and(|found| found.id() == at.id())
            };
            return match kind {
                "variable_declarator"
                | "function_declaration"
                | "generator_function_declaration"
                | "class_declaration"
                | "abstract_class_declaration"
                | "function_expression"
                | "generator_function"
                | "class"
                | "enum_declaration"
                | "internal_module" => field("name"),
                "arrow_function" => field("parameter"),
                "catch_clause" => field("parameter"),
                "for_in_statement" => field("left") && parent.child_by_field_name("kind").is_some(),
                _ => true,
            };
        }
        if !PATTERNS.contains(&kind) || !pattern_part(parent, at) {
            return false;
        }
        at = parent;
    }
    false
}

/// `at` is the bound part of the pattern `parent`, not a default value or a key.
fn pattern_part(parent: Node, at: Node) -> bool {
    let is = |name: &str| {
        parent
            .child_by_field_name(name)
            .is_some_and(|found| found.id() == at.id())
    };
    match Node::kind(&parent) {
        "assignment_pattern" | "object_assignment_pattern" => is("left"),
        "required_parameter" | "optional_parameter" => is("pattern"),
        "pair_pattern" => is("value"),
        _ => true,
    }
}
