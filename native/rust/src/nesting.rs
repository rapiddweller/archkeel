// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A cheap check before `syn` reads a file: how deep do the brackets nest?
//!
//! `syn` and the walk over its tree use one stack frame for each level, so a file of 2,000 nested
//! brackets ends the process. Such a file is UNKNOWN, as a file with a syntax error is. The check
//! skips comments, strings and characters, so a text such as `"((("` does not count.

/// The deepest nesting of `()`, `[]` and `{}` that the scan reads. The deepest file of the `uv`
/// corpus (764 files) nests 22 levels.
pub(crate) const MAX_NESTING: usize = 256;

/// Whether the brackets of `text` nest deeper than `MAX_NESTING`.
pub(crate) fn too_deep(text: &str) -> bool {
    let bytes = text.as_bytes();
    let (mut at, mut depth) = (0, 0_usize);
    while let Some(&byte) = bytes.get(at) {
        at = match byte {
            b'/' if bytes.get(at + 1) == Some(&b'/') => line_end(bytes, at),
            b'/' if bytes.get(at + 1) == Some(&b'*') => comment_end(bytes, at),
            b'"' => quote_end(bytes, at, 0),
            b'r' if starts_raw(bytes, at) => raw_end(bytes, at),
            b'\'' => character_end(bytes, at),
            b'(' | b'[' | b'{' => {
                depth += 1;
                if depth > MAX_NESTING {
                    return true;
                }
                at + 1
            }
            b')' | b']' | b'}' => {
                depth = depth.saturating_sub(1);
                at + 1
            }
            _ => at + 1,
        };
    }
    false
}

fn line_end(bytes: &[u8], from: usize) -> usize {
    bytes[from..]
        .iter()
        .position(|byte| *byte == b'\n')
        .map_or(bytes.len(), |offset| from + offset)
}

/// A block comment nests in Rust.
fn comment_end(bytes: &[u8], from: usize) -> usize {
    let (mut at, mut level) = (from + 2, 1_usize);
    while level > 0 && at < bytes.len() {
        match (bytes.get(at), bytes.get(at + 1)) {
            (Some(b'/'), Some(b'*')) => {
                level += 1;
                at += 2;
            }
            (Some(b'*'), Some(b'/')) => {
                level -= 1;
                at += 2;
            }
            _ => at += 1,
        }
    }
    at.min(bytes.len())
}

/// The end of a string whose quote is at `from`, which `hashes` `#` must follow.
fn quote_end(bytes: &[u8], from: usize, hashes: usize) -> usize {
    let mut at = from + 1;
    while let Some(&byte) = bytes.get(at) {
        if byte == b'\\' && hashes == 0 {
            at += 2;
        } else if byte == b'"' && bytes[at + 1..].iter().take(hashes).all(|b| *b == b'#') {
            return at + 1 + hashes;
        } else {
            at += 1;
        }
    }
    bytes.len()
}

fn starts_raw(bytes: &[u8], at: usize) -> bool {
    let before = at.checked_sub(1).and_then(|index| bytes.get(index));
    let in_name = before.is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_');
    let after = bytes[at + 1..].iter().position(|byte| *byte != b'#');
    !in_name && after.and_then(|offset| bytes.get(at + 1 + offset)) == Some(&b'"')
}

fn raw_end(bytes: &[u8], from: usize) -> usize {
    let hashes = bytes[from + 1..]
        .iter()
        .take_while(|byte| **byte == b'#')
        .count();
    quote_end(bytes, from + 1 + hashes, hashes)
}

/// `'a'` and `'\n'` are characters; `'a` is a lifetime and has no closing quote.
fn character_end(bytes: &[u8], from: usize) -> usize {
    match (bytes.get(from + 1), bytes.get(from + 2)) {
        (Some(b'\\'), _) => bytes[from + 2..]
            .iter()
            .position(|byte| *byte == b'\'')
            .map_or(from + 1, |offset| from + 3 + offset),
        (Some(_), Some(b'\'')) => from + 3,
        _ => from + 1,
    }
}

#[cfg(test)]
#[path = "nesting_tests.rs"]
mod tests;
