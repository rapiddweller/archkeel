// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The parse budget of the survey (AD-454, #1097). The grammar keeps about 2 KB for each token
//! of a dense source, so one source is bounded by its bytes and its possible tokens, and the
//! survey by the total bytes that it parses. A bracket depth over the tree limit of the parse
//! (`MAX_DEPTH`) is a syntax gap of the parse anyway; the survey stops it before the slow parse. A source over a bound is not parsed: it gets the
//! named gap `DartParseBudget`, never a silent skip.

use crate::parse::MAX_DEPTH;

/// The bytes of one source.
pub const PARSE_BUDGET_BYTES: usize = 1 << 20;
/// The possible tokens of one source: each word run and each other byte that is not white space.
pub const PARSE_BUDGET_TOKENS: usize = 1 << 17;
/// The bytes that one survey parses in total.
pub const SURVEY_BUDGET_BYTES: usize = 32 << 20;

/// The bounds of one survey and the bytes that it has parsed.
#[derive(Clone, Copy, Debug)]
pub(crate) struct Budget {
    pub(crate) bytes: usize,
    pub(crate) tokens: usize,
    pub(crate) total: usize,
    pub(crate) spent: usize,
}

impl Default for Budget {
    fn default() -> Self {
        Self {
            bytes: PARSE_BUDGET_BYTES,
            tokens: PARSE_BUDGET_TOKENS,
            total: SURVEY_BUDGET_BYTES,
            spent: 0,
        }
    }
}

impl Budget {
    /// Charge `content`, or give the reason why it is not parsed.
    pub(crate) fn charge(&mut self, content: &[u8]) -> Result<(), String> {
        let size = content.len();
        if size > self.bytes {
            return Err(format!("the source has more than {} bytes", self.bytes));
        }
        if self.spent.saturating_add(size) > self.total {
            return Err(format!(
                "the survey parses more than {} bytes in total",
                self.total
            ));
        }
        if bracket_depth(content) > MAX_DEPTH {
            return Err(format!(
                "the source nests brackets deeper than {MAX_DEPTH} levels"
            ));
        }
        if possible_tokens(content) > self.tokens {
            return Err(format!(
                "the source has more than {} possible tokens",
                self.tokens
            ));
        }
        self.spent = self.spent.saturating_add(size);
        Ok(())
    }
}

/// The deepest bracket level, counted on every byte. A bracket in a string or a comment can make
/// the count wrong in both ways; the parse still decides the syntax, so a low count costs time only.
fn bracket_depth(content: &[u8]) -> usize {
    let mut depth = 0usize;
    let mut deepest = 0usize;
    for byte in content {
        match byte {
            b'(' | b'[' | b'{' => {
                depth = depth.saturating_add(1);
                deepest = deepest.max(depth);
            }
            b')' | b']' | b'}' => depth = depth.saturating_sub(1),
            _ => {}
        }
    }
    deepest
}

/// The count of possible tokens: a byte that is not white space and does not continue a word.
fn possible_tokens(content: &[u8]) -> usize {
    let word = |byte: u8| byte.is_ascii_alphanumeric() || byte == b'_';
    let before = std::iter::once(b' ').chain(content.iter().copied());
    content
        .iter()
        .zip(before)
        .filter(|(byte, previous)| {
            !byte.is_ascii_whitespace() && !(word(**byte) && word(*previous))
        })
        .count()
}

#[cfg(test)]
mod tests {
    use super::{bracket_depth, possible_tokens, Budget, MAX_DEPTH};

    #[test]
    fn a_source_deeper_than_the_tree_limit_is_not_parsed() {
        assert_eq!(bracket_depth(b"f([{}]) {}"), 3);
        let deep = format!("{}{}", "{".repeat(MAX_DEPTH + 1), "}".repeat(MAX_DEPTH + 1));
        assert!(Budget::default().charge(deep.as_bytes()).is_err());
        let flat = "{}".repeat(MAX_DEPTH + 1);
        assert!(Budget::default().charge(flat.as_bytes()).is_ok());
    }

    #[test]
    fn a_word_run_is_one_token_and_punctuation_is_one_each() {
        assert_eq!(possible_tokens(b"var x = [1, 22];"), 9);
        assert_eq!(possible_tokens(b"  \n"), 0);
    }

    #[test]
    fn the_total_bound_stops_the_source_that_passes_it() {
        let mut budget = Budget {
            total: 10,
            ..Budget::default()
        };
        assert!(budget.charge(b"0123456").is_ok());
        assert!(budget.charge(b"0123").is_err());
        assert!(budget.charge(b"012").is_ok());
    }
}
