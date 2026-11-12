// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The text rules of Python `str` that more than one native collector uses. A collector crate
//! never uses another collector crate (AD-327), so a rule that two collectors share lives here.

#![deny(unreachable_pub)]

/// `str.splitlines()`: the lines without their line breaks.
pub fn splitlines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((at, c)) = chars.next() {
        let breaks = matches!(
            c,
            '\n' | '\r'
                | '\u{b}'
                | '\u{c}'
                | '\u{1c}'
                | '\u{1d}'
                | '\u{1e}'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        );
        if !breaks {
            continue;
        }
        lines.push(text.get(start..at).unwrap_or(""));
        let crlf = c == '\r' && chars.peek().is_some_and(|(_, next)| *next == '\n');
        if crlf {
            chars.next();
        }
        start = at
            .saturating_add(c.len_utf8())
            .saturating_add(usize::from(crlf));
    }
    if start < text.len() {
        lines.push(text.get(start..).unwrap_or(""));
    }
    lines
}

/// `str.rstrip()`: Unicode white space plus the four Python separators.
pub fn rstrip(text: &str) -> &str {
    text.trim_end_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
}

#[cfg(test)]
mod tests {
    use super::splitlines;

    // The expected values come from Python 3.11 `str.splitlines`.
    #[test]
    fn splitlines_breaks_where_python_breaks() {
        assert_eq!(splitlines("a\nb\r\nc\rd"), ["a", "b", "c", "d"]);
        assert_eq!(splitlines("a\n\nb\n"), ["a", "", "b"]);
        assert_eq!(
            splitlines("a\u{0b}b\u{0c}c\u{1c}d\u{1d}e\u{1e}f\u{85}g\u{2028}h\u{2029}i"),
            ["a", "b", "c", "d", "e", "f", "g", "h", "i"]
        );
        assert_eq!(splitlines(""), Vec::<&str>::new());
        assert_eq!(splitlines("\r\n"), [""]);
        assert_eq!(splitlines("\r\r\n"), ["", ""]);
        // U+001F and U+00A0 are white space, but not line breaks.
        assert_eq!(splitlines("a\u{1f}b\u{a0}c"), ["a\u{1f}b\u{a0}c"]);
    }
}
