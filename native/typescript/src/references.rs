// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module references of one file: `import`, `export ... from`, `import()`, `require()`.
//!
//! One query finds the nodes. A reference inside a region that the parser had to repair is not
//! a fact, so it is dropped (`parse._in_error`).

use tree_sitter::Node;

use crate::scan::Scan;
use crate::source::{Source, Span};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Form {
    Import,
    Reexport,
    ImportEquals,
    DynamicImport,
    ImportType,
    Require,
}

impl Form {
    pub fn as_str(self) -> &'static str {
        match self {
            Form::Import => "import",
            Form::Reexport => "reexport",
            Form::ImportEquals => "import_equals",
            Form::DynamicImport => "dynamic_import",
            Form::ImportType => "import_type",
            Form::Require => "require",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Reference {
    pub form: Form,
    /// `None` when the argument is not a plain string, so no module can be named.
    pub specifier: Option<String>,
    pub type_only: bool,
    pub module_level: bool,
    /// A `resolution-mode` attribute replaces the mode that a resolver would derive.
    pub mode_override: bool,
    pub span: Span,
}

fn children<'t>(node: Option<Node<'t>>, kind: &str) -> Vec<Node<'t>> {
    node.map(|node| {
        crate::members::children(node)
            .into_iter()
            .filter(|child| child.kind() == kind)
            .collect()
    })
    .unwrap_or_default()
}

fn has_type_keyword(node: Node) -> bool {
    crate::members::children(node)
        .into_iter()
        .any(|child| child.kind() == "type")
}

/// `parse._in_error`: the node holds a repair, or lies inside one.
pub fn in_error(node: Node) -> bool {
    if node.has_error() {
        return true;
    }
    let mut parent = node.parent();
    while let Some(current) = parent {
        if current.is_error() {
            return true;
        }
        parent = current.parent();
    }
    false
}

/// `parse._literal`: the module text of a string without escapes or substitutions.
pub fn literal(node: Option<Node>, source: &Source) -> Option<String> {
    let node = node.filter(|node| matches!(node.kind(), "string" | "template_string"))?;
    let text = source.text(node);
    if text.contains('\\') {
        return None;
    }
    if crate::members::children(node)
        .into_iter()
        .any(|child| child.kind() == "template_substitution")
    {
        return None;
    }
    let mut chars = text.chars();
    chars.next();
    chars.next_back();
    Some(chars.as_str().to_owned())
}

/// `import type`, or every named specifier marked `type` with no default import.
fn type_only(statement: Node, specifiers: &[Node], default: bool) -> bool {
    let marked = !specifiers.is_empty() && specifiers.iter().all(|item| has_type_keyword(*item));
    has_type_keyword(statement) || (marked && !default)
}

fn top_level(node: Node) -> bool {
    node.parent()
        .is_some_and(|parent| parent.kind() == "program")
}

fn mode_override(node: Node, source: &Source) -> bool {
    source.text(node).contains("resolution-mode")
}

fn import(node: Node, source: &Source) -> Reference {
    let clause = children(Some(node), "import_clause").into_iter().next();
    let required = children(Some(node), "import_require_clause")
        .into_iter()
        .next();
    let named = children(
        children(clause, "named_imports").into_iter().next(),
        "import_specifier",
    );
    let holder = required.unwrap_or(node);
    let string = children(Some(holder), "string").into_iter().next();
    Reference {
        form: if required.is_none() {
            Form::Import
        } else {
            Form::ImportEquals
        },
        specifier: literal(string, source),
        type_only: type_only(node, &named, !children(clause, "identifier").is_empty()),
        module_level: top_level(node),
        mode_override: mode_override(node, source),
        span: source.span(node, None),
    }
}

fn export(node: Node, source: &Source) -> Reference {
    let clause = children(Some(node), "export_clause").into_iter().next();
    let string = children(Some(node), "string").into_iter().next();
    Reference {
        form: Form::Reexport,
        specifier: literal(string, source),
        type_only: type_only(node, &children(clause, "export_specifier"), false),
        module_level: top_level(node),
        mode_override: mode_override(node, source),
        span: source.span(node, None),
    }
}

/// `parse._argument`: the first named child of the arguments, which can be a comment.
fn argument(call: Node) -> Option<Node> {
    let arguments = children(Some(call), "arguments").into_iter().next()?;
    arguments.named_child(0)
}

const TYPE_PARENTS: [&str; 7] = [
    "type_annotation",
    "type_arguments",
    "type_query",
    "type_alias_declaration",
    "type_parameter",
    "extends_type_clause",
    "implements_clause",
];

/// `parse._in_type`: a module named in a type is a type-only reference.
fn in_type(node: Node) -> bool {
    let (mut child, mut parent) = (node, node.parent());
    while let Some(current) = parent {
        if TYPE_PARENTS.contains(&current.kind()) {
            return true;
        }
        // `value as T` and `value satisfies T` start with the value; only what follows is a type.
        if matches!(current.kind(), "as_expression" | "satisfies_expression")
            && child.start_byte() > current.start_byte()
        {
            return true;
        }
        (child, parent) = (current, current.parent());
    }
    false
}

/// The `typeof` query that an import type opens, which the compiler counts as part of it.
fn query_start(node: Node) -> Option<Node> {
    let mut parent = node.parent();
    while let Some(current) = parent {
        let chain = matches!(
            current.kind(),
            "member_expression" | "call_expression" | "subscript_expression"
        );
        if !(chain && current.start_byte() == node.start_byte()) {
            break;
        }
        parent = current.parent();
    }
    parent.filter(|node| node.kind() == "type_query")
}

fn dynamic(node: Node, source: &Source) -> Reference {
    let typed = in_type(node);
    Reference {
        form: if typed {
            Form::ImportType
        } else {
            Form::DynamicImport
        },
        specifier: literal(argument(node), source),
        type_only: typed,
        module_level: false,
        mode_override: mode_override(node, source),
        span: source.span(node, typed.then(|| query_start(node)).flatten()),
    }
}

fn require(node: Node, source: &Source) -> Reference {
    Reference {
        form: Form::Require,
        specifier: literal(argument(node), source),
        type_only: false,
        module_level: false,
        mode_override: false,
        span: source.span(node, None),
    }
}

/// The trusted references of a file, in the order of their position.
pub fn trusted(source: &Source, root: Node, scan: &Scan) -> Vec<Reference> {
    let mut candidates: Vec<(Node, Reference)> = Vec::new();
    candidates.extend(scan.imports.iter().map(|n| (*n, import(*n, source))));
    candidates.extend(scan.exports.iter().map(|n| (*n, export(*n, source))));
    candidates.extend(scan.dynamic.iter().map(|n| (*n, dynamic(*n, source))));
    candidates.extend(scan.requires.iter().map(|n| (*n, require(*n, source))));
    let broken = root.has_error();
    let mut kept: Vec<Reference> = candidates
        .into_iter()
        .filter(|(node, _)| !(broken && in_error(*node)))
        .map(|(_, reference)| reference)
        .collect();
    kept.sort_by(|left, right| {
        let key = |item: &Reference| (item.span.line, item.span.column, item.form.as_str());
        key(left).cmp(&key(right))
    });
    kept
}
