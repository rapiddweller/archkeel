// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shared CPython definition location, after the decorator list.

use ruff_python_ast::{Stmt, StmtClassDef, StmtFunctionDef};
use ruff_text_size::{Ranged, TextRange, TextSize};

#[derive(Clone, Copy)]
pub(crate) enum Def<'a> {
    Function(&'a StmtFunctionDef),
    Class(&'a StmtClassDef),
}

impl<'a> Def<'a> {
    pub(crate) fn name(&self) -> &'a str {
        match self {
            Def::Function(node) => node.name.as_str(),
            Def::Class(node) => node.name.as_str(),
        }
    }

    pub(crate) fn body(&self) -> &'a [Stmt] {
        match self {
            Def::Function(node) => &node.body,
            Def::Class(node) => &node.body,
        }
    }

    pub(crate) fn range(&self, source: &str) -> TextRange {
        let (range, decorators) = match self {
            Def::Function(node) => (node.range, node.decorator_list.last()),
            Def::Class(node) => (node.range, node.decorator_list.last()),
        };
        let start = decorators.map_or(range.start(), |last| keyword(source, last.end()));
        TextRange::new(start.min(range.end()), range.end())
    }
}

fn keyword(source: &str, from: TextSize) -> TextSize {
    let bytes = source.as_bytes();
    let mut at = from.to_usize();
    while let Some(&byte) = bytes.get(at) {
        match byte {
            b' ' | b'\t' | b'\n' | b'\r' | b'\x0c' | b'\\' => at += 1,
            b'#' => {
                while bytes
                    .get(at)
                    .is_some_and(|byte| *byte != b'\n' && *byte != b'\r')
                {
                    at += 1;
                }
            }
            _ => break,
        }
    }
    TextSize::try_from(at).unwrap_or(from)
}
