// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Read the module references and the unprovable patterns of one file (`parse.parse`).

use crate::concerns::{self, Concern};
use crate::references::{self, Reference};
use crate::scan::scan;
use crate::script;
use crate::source::Source;
use crate::source_input::{classify_file, Reach};
use crate::syntax::Parsers;
use crate::tree::cx::Cx;
use crate::walk::{Syntax, Walk};

pub(crate) struct Parsed {
    /// The composition must discard the run when the requested bracket-nesting limit was hit.
    pub depth_limited: bool,
    pub references: Vec<Reference>,
    /// The number of import-bearing nodes of the tree, to check that each has an outcome.
    pub places: usize,
    pub concerns: Vec<Concern>,
    /// A `require` name that is not a plain call may be a local binding, not the loader.
    pub shadows_require: bool,
    /// The line of the first repair that the parser made.
    pub first_error: Option<i64>,
    /// The scopes, definitions, import bindings and exports of the file. The reply carries
    /// them under `inner-uml-v1`; the `dump` feature prints them (AD-323).
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    pub syntax: Syntax,
}

/// Parse one file of a project without `paths` and `baseUrl`; the dump and the tests read it.
#[cfg(any(test, feature = "dump"))]
pub(crate) fn parse(parsers: &mut Parsers, rel: &str, data: &[u8]) -> Parsed {
    let reach = Reach {
        aliased: false,
        type_roots: false,
    };
    parse_for(parsers, rel, data, reach, None)
}

/// Parse one file of a project; `reach` says which options can map a name to a project file.
pub(crate) fn parse_for(
    parsers: &mut Parsers,
    rel: &str,
    data: &[u8],
    reach: Reach,
    max_bracket_depth: Option<usize>,
) -> Parsed {
    // The filename test of the Python collector ignores one final newline.
    let suffix = classify_file(rel.strip_suffix('\n').unwrap_or(rel));
    // JSX and JavaScript need the TSX grammar; `<T>x` assertions exist only without it.
    let typescript = suffix.is_some_and(|suffix| suffix.parser_typescript());
    let parsed = parsers.parse(typescript, data);
    let depth_limited = parsed.as_ref().is_some_and(|(tree, _)| {
        max_bracket_depth.is_some_and(|limit| brackets_too_deep(tree.root_node(), limit))
    });
    let parsed = parsed.filter(|_| !depth_limited);
    let Some((tree, grammar)) = parsed else {
        return Parsed {
            depth_limited,
            references: Vec::new(),
            places: 0,
            concerns: Vec::new(),
            shadows_require: false,
            first_error: Some(1),
            syntax: Syntax::empty(),
        };
    };
    let source = Source::new(data);
    let root = tree.root_node();
    let cx = Cx {
        kinds: &grammar.map,
        source: &source,
    };
    let mut walk = Walk::new(cx);
    let found_nodes = scan(&grammar.kinds, &source, root, &mut walk);
    let layout = walk.take_layout();
    let mut syntax = walk.finish(root, suffix);
    let (found_script, ambiguous) = script::read(cx, root, layout, &syntax, &grammar.templates);
    syntax.script = found_script;
    let extracted = references::trusted(&source, root, &found_nodes);
    let references = extracted.trusted;
    let mut found = concerns::read(
        &source,
        root,
        &found_nodes,
        &references,
        suffix,
        (syntax.module_syntax, reach),
    );
    // `parse.parse`: after the comment concerns, one for each scope that binds names unknowably.
    found
        .list
        .extend(ambiguous.into_iter().map(|span| concerns::Concern {
            reason: "Script binding scope is not statically known".to_owned(),
            span,
        }));
    let first_error = found_nodes
        .errors
        .iter()
        .min_by_key(|node| node.start_byte())
        .map(|node| source.span(*node, None).line);
    Parsed {
        depth_limited: false,
        references,
        places: grammar.places.count(&source, root),
        concerns: found.list,
        shadows_require: found.shadows_require,
        first_error,
        syntax,
    }
}

fn brackets_too_deep(root: tree_sitter::Node<'_>, limit: usize) -> bool {
    let (mut cursor, mut depth) = (root.walk(), 0);
    loop {
        depth += usize::from(bracketed(cursor.node()));
        if depth > limit {
            return true;
        }
        if cursor.goto_first_child() {
            continue;
        }
        loop {
            depth -= usize::from(bracketed(cursor.node()));
            if cursor.goto_next_sibling() {
                break;
            }
            if !cursor.goto_parent() {
                return false;
            }
        }
    }
}

fn bracketed(node: tree_sitter::Node<'_>) -> bool {
    // Expression/statement chains deepen the AST without nesting source delimiters.
    matches!(
        node.kind(),
        "arguments"
            | "formal_parameters"
            | "parenthesized_expression"
            | "parenthesized_type"
            | "statement_block"
            | "class_body"
            | "object"
            | "object_pattern"
            | "object_type"
            | "array"
            | "array_pattern"
            | "tuple_type"
            | "type_arguments"
            | "type_parameters"
            | "jsx_element"
            | "jsx_fragment"
            | "jsx_expression"
    )
}

#[cfg(test)]
#[path = "parse_tests.rs"]
mod tests;
