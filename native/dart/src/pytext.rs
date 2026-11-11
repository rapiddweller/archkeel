// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The text rules of Python `str` that the Python Dart collector uses, so that both collectors
//! split and strip a text in the same places.

/// `str.isspace` and the `\s` of `re`: the White_Space characters and U+001C to U+001F.
pub(crate) fn is_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// Python `\w` for a text: a letter, a digit or an underscore.
pub(crate) fn is_word(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
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
    let is_word = |b: &u8| b.is_ascii_alphanumeric() || *b == b'_';
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
    raw.iter()
        .all(|byte| matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c))
}

#[cfg(test)]
#[path = "pytext_tests.rs"]
mod tests;
