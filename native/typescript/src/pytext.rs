// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Text rules of Python 3, which the Python collector uses and this collector must repeat.

use std::borrow::Cow;

// `str.isspace`: what Python `\s` and `str.rstrip()` match.
const SPACE: &str = "\t\n\u{b}\u{c}\r\u{1c}\u{1d}\u{1e}\u{1f} \u{85}\u{a0}\u{1680}\u{2000}\u{2001}\u{2002}\u{2003}\u{2004}\u{2005}\u{2006}\u{2007}\u{2008}\u{2009}\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}";

pub fn is_space(c: char) -> bool {
    SPACE.contains(c)
}

/// Python `\w` for a text: a letter, a digit or an underscore.
pub fn is_word(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

/// `str(data, "utf-8", "replace")`.
pub fn decode(data: &[u8]) -> Cow<'_, str> {
    String::from_utf8_lossy(data)
}

/// The length of a text in UTF-16 code units, as the compiler counts a column.
pub fn utf16_len(text: &str) -> usize {
    text.chars().map(char::len_utf16).sum()
}

/// `text[:count]` for code points.
pub fn first_chars(text: &str, count: usize) -> &str {
    match text.char_indices().nth(count) {
        Some((end, _)) => &text[..end],
        None => text,
    }
}
