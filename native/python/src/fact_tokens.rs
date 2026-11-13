// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Bounded source token positions for lexical locations and typing comments.

use ruff_python_ast::token::TokenKind;
use ruff_python_parser::{lexer::lex, Mode};
use ruff_text_size::{TextRange, TextSize};
use std::collections::BTreeMap;

use super::work::Work;

pub struct Tokens {
    pub significant: Vec<(TokenKind, TextRange)>,
    pub comments: Vec<TextRange>,
    pub parentheses: BTreeMap<TextSize, TextSize>,
}

pub fn tokens(source: &str, work: &mut Work) -> Result<Tokens, String> {
    if !work.charge(source.len()) {
        return Err("source token work limit exceeded".into());
    }
    let mut lexer = lex(source, Mode::Module);
    let mut found = Tokens {
        significant: Vec::new(),
        comments: Vec::new(),
        parentheses: BTreeMap::new(),
    };
    let mut opened = Vec::new();
    loop {
        if !work.charge(1) {
            return Err("source token work limit exceeded".into());
        }
        let kind = lexer.next_token();
        if kind == TokenKind::EndOfFile {
            return Ok(found);
        }
        if kind == TokenKind::Lpar {
            opened.push(lexer.current_range().start());
        }
        if kind == TokenKind::Rpar {
            if let Some(start) = opened.pop() {
                found.parentheses.insert(start, lexer.current_range().end());
            }
        }
        if kind == TokenKind::Comment {
            found.comments.push(lexer.current_range());
        }
        if !kind.is_trivia() && !kind.is_any_newline() {
            found.significant.push((kind, lexer.current_range()));
        }
    }
}
