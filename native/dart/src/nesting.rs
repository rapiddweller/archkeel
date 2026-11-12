// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A bound on the memory of the parse (AD-376). Tree-sitter keeps a stack entry for each open
//! bracket until the bracket closes, about a kilobyte each, so a hostile source of nested brackets
//! takes gigabytes before the first rule runs. A byte count of the open brackets is cheap and
//! needs no tree.

use crate::parse::MAX_DEPTH;

/// The open brackets that a source may hold at one byte: ten times `MAX_DEPTH`. A tree that
/// passes `MAX_DEPTH` has a gap already; this bound only stops the parse of a source far past it.
/// It counts the brackets in strings and comments too, so it is stricter than the tree.
pub(crate) const MAX_BRACKETS: usize = MAX_DEPTH * 10;

/// The byte where the open brackets of `data` first pass `MAX_BRACKETS`: `(`, `[` and `{` open,
/// `)`, `]` and `}` close, and a close at zero stays at zero.
pub(crate) fn brackets_overflow(data: &[u8]) -> Option<usize> {
    let mut open = 0usize;
    for (at, byte) in data.iter().enumerate() {
        match byte {
            b'(' | b'[' | b'{' => {
                open = open.saturating_add(1);
                if open > MAX_BRACKETS {
                    return Some(at);
                }
            }
            b')' | b']' | b'}' => open = open.saturating_sub(1),
            _ => {}
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_count_passes_the_bound_at_one_byte() {
        let text = "(".repeat(MAX_BRACKETS + 1);
        assert_eq!(brackets_overflow(text.as_bytes()), Some(MAX_BRACKETS));
        assert_eq!(brackets_overflow(&text.as_bytes()[1..]), None);
    }

    #[test]
    fn a_closed_bracket_lowers_the_count_and_never_below_zero() {
        let text = format!("{}{}", ")".repeat(MAX_BRACKETS), "[".repeat(MAX_BRACKETS));
        assert_eq!(brackets_overflow(text.as_bytes()), None);
        let mixed = format!("{{{}", "(".repeat(MAX_BRACKETS));
        assert_eq!(brackets_overflow(mixed.as_bytes()), Some(MAX_BRACKETS));
    }
}
