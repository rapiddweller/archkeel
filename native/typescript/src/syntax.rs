// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The grammar of one file, as `parse.py` reads it.
//!
//! This is the only module that touches the parser. The parser runs inside the collector
//! process, which the host bounds, because it reads untrusted source.

use tree_sitter::{Language, Parser};
use tree_sitter_typescript::{LANGUAGE_TSX, LANGUAGE_TYPESCRIPT};

use crate::kinds::KindMap;
use crate::scan::Kinds;
use crate::umd::Templates;

/// One grammar with the node kinds that import extraction matches.
pub struct Grammar {
    pub language: Language,
    pub kinds: Kinds,
    /// The kind of each node id, for the syntax walk.
    pub map: KindMap,
    /// The templates that a script matches exactly (`umd.rs`).
    pub templates: Templates,
}

impl Grammar {
    fn new(language: Language) -> Self {
        Self {
            kinds: Kinds::new(&language),
            map: KindMap::new(&language),
            templates: Templates::new(&language),
            language,
        }
    }
}

/// The parser, the two grammars and their queries, built once for a collection.
pub struct Parsers {
    parser: Parser,
    typescript: Grammar,
    tsx: Grammar,
}

impl Parsers {
    pub fn new() -> Self {
        Self {
            parser: Parser::new(),
            typescript: Grammar::new(LANGUAGE_TYPESCRIPT.into()),
            tsx: Grammar::new(LANGUAGE_TSX.into()),
        }
    }

    /// Parse with the grammar without JSX when `typescript` is set, else with the TSX grammar.
    pub fn parse(
        &mut self,
        typescript: bool,
        data: &[u8],
    ) -> Option<(tree_sitter::Tree, &Grammar)> {
        let grammar = if typescript {
            &self.typescript
        } else {
            &self.tsx
        };
        self.parser.set_language(&grammar.language).ok()?;
        Some((self.parser.parse(data, None)?, grammar))
    }
}
