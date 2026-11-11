// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Read the module references and the unprovable patterns of one file (`parse.parse`).

use crate::concerns::{self, Concern};
use crate::references::{self, Reference};
use crate::scan::scan;
use crate::script;
use crate::source::Source;
use crate::source_input::classify_file;
use crate::syntax::Parsers;
use crate::tree::cx::Cx;
use crate::walk::{Syntax, Walk};

pub struct Parsed {
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
pub fn parse(parsers: &mut Parsers, rel: &str, data: &[u8]) -> Parsed {
    parse_for(parsers, rel, data, false)
}

/// Parse one file of a project that sets `paths` or `baseUrl` (`aliased`) or does not (#976).
pub fn parse_for(parsers: &mut Parsers, rel: &str, data: &[u8], aliased: bool) -> Parsed {
    // The filename test of the Python collector ignores one final newline.
    let suffix = classify_file(rel.strip_suffix('\n').unwrap_or(rel));
    // JSX and JavaScript need the TSX grammar; `<T>x` assertions exist only without it.
    let typescript = suffix.is_some_and(|suffix| suffix.parser_typescript());
    let Some((tree, grammar)) = parsers.parse(typescript, data) else {
        return Parsed {
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
        (syntax.module_syntax, aliased),
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
        references,
        places: grammar.places.count(&source, root),
        concerns: found.list,
        shadows_require: found.shadows_require,
        first_error,
        syntax,
    }
}

#[cfg(test)]
#[path = "parse_tests.rs"]
mod tests;
