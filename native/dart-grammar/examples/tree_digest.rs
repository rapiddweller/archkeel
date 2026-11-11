// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Rust half of the Dart grammar parity check (AD-342, `tools/dart_grammar_parity.py`).
//!
//! Read one file path on each line of stdin. Parse each file with the vendored grammar and write
//! one line: the SHA-256 of the tree text, a tab, the parse time in nanoseconds. The tree text
//! has one line for each node in preorder, with all anonymous nodes:
//! `depth kind named field start_byte end_byte missing extra`. The Python half writes the same
//! text with `tree_sitter_dart`, so two equal digests mean two equal trees.

use std::fmt::Write as _;
use std::io::{self, BufRead, Write};
use std::time::Instant;

use sha2::{Digest, Sha256};
use tree_sitter::{Parser, Tree};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut parser = Parser::new();
    parser.set_language(&archkeel_dart_grammar::LANGUAGE.into())?;
    let stdout = io::stdout();
    let mut out = stdout.lock();
    for line in io::stdin().lock().lines() {
        let path = line?;
        let source = std::fs::read(&path)?;
        let started = Instant::now();
        let tree = parser
            .parse(&source, None)
            .ok_or_else(|| format!("no tree for {path}"))?;
        let nanos = started.elapsed().as_nanos();
        let digest: String = Sha256::digest(tree_text(&tree)?.as_bytes())
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        writeln!(out, "{digest}\t{nanos}")?;
    }
    Ok(())
}

fn tree_text(tree: &Tree) -> Result<String, std::fmt::Error> {
    let mut text = String::new();
    let mut cursor = tree.walk();
    let mut depth = 0_usize;
    loop {
        let node = cursor.node();
        writeln!(
            text,
            "{depth} {} {} {} {} {} {} {}",
            node.kind(),
            u8::from(node.is_named()),
            cursor.field_name().unwrap_or("-"),
            node.start_byte(),
            node.end_byte(),
            u8::from(node.is_missing()),
            u8::from(node.is_extra()),
        )?;
        if cursor.goto_first_child() {
            depth += 1;
            continue;
        }
        while !cursor.goto_next_sibling() {
            if !cursor.goto_parent() {
                return Ok(text);
            }
            depth -= 1;
        }
    }
}
