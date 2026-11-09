// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Read the module references and the unprovable patterns of one file (`parse.parse`).

use crate::concerns::{self, Concern};
use crate::members::Cx;
use crate::references::{self, Reference};
use crate::scan::scan;
use crate::source::Source;
use crate::source_input::classify_file;
use crate::syntax::Parsers;
use crate::walk::{Syntax, Walk};

pub struct Parsed {
    pub references: Vec<Reference>,
    pub concerns: Vec<Concern>,
    /// A `require` name that is not a plain call may be a local binding, not the loader.
    pub shadows_require: bool,
    /// The line of the first repair that the parser made.
    pub first_error: Option<i64>,
    /// The scopes, definitions, import bindings and exports of the file. The reply does not carry
    /// them yet; the `dump` feature prints them (AD-323).
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    pub syntax: Syntax,
}

/// Parse one file. `data` is the text as the Python collector re-encodes it.
pub fn parse(parsers: &mut Parsers, rel: &str, data: &[u8]) -> Parsed {
    // The filename test of the Python collector ignores one final newline.
    let suffix = classify_file(rel.strip_suffix('\n').unwrap_or(rel));
    // JSX and JavaScript need the TSX grammar; `<T>x` assertions exist only without it.
    let typescript = suffix.is_some_and(|suffix| suffix.parser_typescript());
    let Some((tree, grammar)) = parsers.parse(typescript, data) else {
        return Parsed {
            references: Vec::new(),
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
    let syntax = walk.finish(root, suffix);
    let references = references::trusted(&source, root, &found_nodes);
    let found = concerns::read(&source, root, &found_nodes, &references, suffix);
    let first_error = found_nodes
        .errors
        .iter()
        .min_by_key(|node| node.start_byte())
        .map(|node| source.span(*node, None).line);
    Parsed {
        references,
        concerns: found.list,
        shadows_require: found.shadows_require,
        first_error,
        syntax,
    }
}

#[cfg(test)]
#[path = "parse_tests.rs"]
mod tests;
