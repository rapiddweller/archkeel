// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A bound on the memory of the parse (AD-376). Tree-sitter keeps a stack entry for each open
//! bracket until the bracket closes, about a kilobyte each, so a hostile source of nested brackets
//! takes gigabytes before the first rule runs. The guard counts opening brackets in the whole
//! source and never counts a closing bracket: a closing bracket in a comment or a string is not
//! one for Tree-sitter, so a count that falls on it could pass a source that is really deep. An
//! unsound lexer for comments and strings would be worse than counting every opener.

/// The opening brackets that a source may hold: at most 100 000 levels, about 120 MB of stack.
/// The corpora hold at most 15 504 in one file. It counts the brackets in strings and comments
/// too, so it is stricter than the tree.
pub(crate) const MAX_OPENERS: usize = 100_000;

/// The byte of the opening bracket that passes `MAX_OPENERS`: `(`, `[` and `{` count.
pub(crate) fn openers_overflow(data: &[u8]) -> Option<usize> {
    let mut open = 0usize;
    for (at, byte) in data.iter().enumerate() {
        if matches!(byte, b'(' | b'[' | b'{') {
            open = open.saturating_add(1);
            if open > MAX_OPENERS {
                return Some(at);
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_count_passes_the_bound_at_one_byte() {
        let text = "(".repeat(MAX_OPENERS + 1);
        assert_eq!(openers_overflow(text.as_bytes()), Some(MAX_OPENERS));
        assert_eq!(openers_overflow(text.as_bytes().get(1..).unwrap()), None);
    }

    #[test]
    fn a_closing_bracket_in_a_comment_or_a_string_never_lowers_the_count() {
        for filler in ["/*)*/", "// )))\n", "')]}'", "]", "}"] {
            let text = format!("({filler}").repeat(MAX_OPENERS + 1);
            assert_eq!(
                openers_overflow(text.as_bytes()).is_some(),
                true,
                "{filler}"
            );
        }
    }
}
