// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The text rules of Python `str` that the Python Dart collector uses, so that both collectors
//! split and strip a text in the same places.

use std::sync::OnceLock;

use crate::unicode_tables::{ASSIGNED, SPACE, WORD};

static WORD_RANGES: OnceLock<Vec<(u32, u32)>> = OnceLock::new();
static SPACE_RANGES: OnceLock<Vec<(u32, u32)>> = OnceLock::new();
static ASSIGNED_RANGES: OnceLock<Vec<(u32, u32)>> = OnceLock::new();

/// The ranges of a generated table text: `START-END` in hex, separated by white space. The
/// generator writes only valid cells; `each_table_equals_the_dump_of_the_oracle` checks them.
pub(crate) fn ranges(text: &str) -> Vec<(u32, u32)> {
    text.split_whitespace()
        .filter_map(|cell| {
            let (start, end) = cell.split_once('-')?;
            let start = u32::from_str_radix(start, 16).ok()?;
            Some((start, u32::from_str_radix(end, 16).ok()?))
        })
        .collect()
}

/// `str.isspace` and the `\s` of `re`, as Python 3.11 with Unicode 14 decides it (L-27).
pub(crate) fn is_space(c: char) -> bool {
    in_table(SPACE_RANGES.get_or_init(|| ranges(SPACE)), c)
}

/// Python `\w` for a text, as Python 3.11 with Unicode 14 decides it (L-27): the table of the
/// oracle, not `char::is_alphanumeric`. The two differ on about 11 000 code points, such as the
/// combining marks U+0345 and U+093E and each letter that Unicode 14 does not assign.
pub(crate) fn is_word(c: char) -> bool {
    in_table(WORD_RANGES.get_or_init(|| ranges(WORD)), c)
}

/// The code point is assigned in Unicode 14, the Unicode version of the oracle Python 3.11.
pub(crate) fn is_assigned(c: char) -> bool {
    in_table(ASSIGNED_RANGES.get_or_init(|| ranges(ASSIGNED)), c)
}

/// The code point is in one of the sorted inclusive ranges of `table`.
pub(crate) fn in_table(table: &[(u32, u32)], c: char) -> bool {
    let code = u32::from(c);
    let after = table.partition_point(|(start, _)| *start <= code);
    after
        .checked_sub(1)
        .and_then(|at| table.get(at))
        .is_some_and(|(_, end)| code <= *end)
}

/// `\w` of a `bytes` pattern: an ASCII letter, an ASCII digit or `_`.
pub(crate) fn is_word_byte(value: u8) -> bool {
    value.is_ascii_alphanumeric() || value == b'_'
}

/// `\s` of a `bytes` pattern and the white space of `bytes.strip`.
pub(crate) fn is_space_byte(value: u8) -> bool {
    matches!(value, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
}

/// `re.search(rf"\b{word}\b", text)` for a word of word characters.
pub(crate) fn has_word(text: &str, word: &str) -> bool {
    text.match_indices(word).any(|(at, _)| {
        let before = text.get(..at).and_then(|head| head.chars().next_back());
        let after = text
            .get(at.saturating_add(word.len())..)
            .and_then(|tail| tail.chars().next());
        !before.is_some_and(is_word) && !after.is_some_and(is_word)
    })
}

/// `re.search(rb"\b{word}\b", data)`: the word test of a `bytes` pattern, ASCII only.
pub(crate) fn has_ascii_word(data: &[u8], word: &[u8]) -> bool {
    let is_word = |b: &u8| is_word_byte(*b);
    data.windows(word.len()).enumerate().any(|(at, window)| {
        window == word
            && !at
                .checked_sub(1)
                .and_then(|before| data.get(before))
                .is_some_and(is_word)
            && !data.get(at.saturating_add(word.len())).is_some_and(is_word)
    })
}

/// `text[:count]` for code points.
pub(crate) fn first_chars(text: &str, count: usize) -> &str {
    match text.char_indices().nth(count) {
        Some((end, _)) => text.get(..end).unwrap_or(text),
        None => text,
    }
}

/// `str.strip()`.
pub(crate) fn strip(text: &str) -> &str {
    text.trim_matches(is_space)
}

/// `str.lstrip()`.
pub(crate) fn lstrip(text: &str) -> &str {
    text.trim_start_matches(is_space)
}

/// `str.rstrip()`.
pub(crate) fn rstrip(text: &str) -> &str {
    text.trim_end_matches(is_space)
}

/// `bytes.strip()` is empty: the bytes hold only ASCII white space.
pub(crate) fn is_blank(raw: &[u8]) -> bool {
    raw.iter().all(|byte| is_space_byte(*byte))
}

#[cfg(test)]
#[path = "pytext_tests.rs"]
mod tests;
