// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The byte rules of Dart strings and comments that `analyzer/dart/parse.py` applies without the
//! tree: the decode of a string literal, the URI of a directive and the unclosed block comment.
//! Each function repeats the Python function of the same name, also where the Python rule is
//! odd: `_string_end` never skips a backslash escape, because its pattern can never match.

use std::borrow::Cow;

use crate::pytext::is_word_byte;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Delimiter {
    Line,
    Open,
    Close,
}

/// `_comment_delimiter`: the comment token at `index`. It reads past `end`, as Python does.
fn delimiter(data: &[u8], index: usize) -> Option<Delimiter> {
    match data.get(index..index.saturating_add(2))? {
        b"//" => Some(Delimiter::Line),
        b"/*" => Some(Delimiter::Open),
        b"*/" => Some(Delimiter::Close),
        _ => None,
    }
}

fn byte(data: &[u8], index: usize) -> Option<u8> {
    data.get(index).copied()
}

fn is_quote(value: Option<u8>) -> bool {
    matches!(value, Some(b'\'' | b'"'))
}

fn is_raw_mark(value: Option<u8>) -> bool {
    matches!(value, Some(b'r' | b'R'))
}

fn starts_with(data: &[u8], prefix: &[u8], index: usize) -> bool {
    data.get(index..)
        .is_some_and(|rest| rest.starts_with(prefix))
}

/// `bytes.find(b"\n", start, end)`.
fn find_newline(data: &[u8], start: usize, end: usize) -> Option<usize> {
    let end = end.min(data.len());
    data.get(start..end)?
        .iter()
        .position(|value| *value == b'\n')
        .map(|at| start.saturating_add(at))
}

/// The quote of a string at `index`: one quote byte or three equal quote bytes.
fn quote_at(data: &[u8], index: usize) -> Option<Vec<u8>> {
    let quote = byte(data, index).filter(|value| is_quote(Some(*value)))?;
    let triple = [quote; 3];
    Some(if starts_with(data, &triple, index) {
        triple.to_vec()
    } else {
        vec![quote]
    })
}

/// One step inside a nested block comment: the depth change of `found` and the bytes to skip.
fn nested_step(found: Option<Delimiter>, depth: &mut usize) -> usize {
    match found {
        Some(Delimiter::Open) => {
            *depth = depth.saturating_add(1);
            2
        }
        Some(Delimiter::Close) => {
            *depth = depth.saturating_sub(1);
            2
        }
        _ => 1,
    }
}

/// `_unclosed_block_comment`: the start of a block comment that the source never closes.
pub(crate) fn unclosed_block_comment(content: &[u8]) -> Option<usize> {
    let mut index = 0usize;
    let mut block_start = None;
    let mut depth = 0usize;
    let mut quote: Vec<u8> = Vec::new();
    let mut raw = false;
    while index < content.len() {
        let found = delimiter(content, index);
        if depth > 0 {
            index = index.saturating_add(nested_step(found, &mut depth));
            if depth == 0 {
                block_start = None;
            }
            continue;
        }
        if !quote.is_empty() {
            if !raw && byte(content, index) == Some(b'\\') {
                index = index.saturating_add(2);
            } else if starts_with(content, &quote, index) {
                index = index.saturating_add(quote.len());
                quote.clear();
                raw = false;
            } else {
                index = index.saturating_add(1);
            }
            continue;
        }
        match found {
            Some(Delimiter::Line) => {
                index = find_newline(content, index.saturating_add(2), content.len())
                    .map_or(content.len(), |at| at.saturating_add(1));
                continue;
            }
            Some(Delimiter::Open) => {
                block_start = Some(index);
                depth = 1;
                index = index.saturating_add(2);
                continue;
            }
            _ => {}
        }
        raw = is_raw_mark(byte(content, index)) && is_quote(byte(content, index.saturating_add(1)));
        if raw {
            index = index.saturating_add(1);
        }
        if let Some(found) = quote_at(content, index) {
            index = index.saturating_add(found.len());
            quote = found;
            continue;
        }
        index = index.saturating_add(1);
    }
    if depth > 0 {
        block_start
    } else {
        None
    }
}

/// `_skip_trivia`: skip white space and comments from `index` up to `end`.
pub(crate) fn skip_trivia(data: &[u8], mut index: usize, end: usize) -> usize {
    while index < end {
        let found = delimiter(data, index);
        if matches!(byte(data, index), Some(b' ' | b'\t' | b'\r' | b'\n')) {
            index = index.saturating_add(1);
        } else if found == Some(Delimiter::Line) {
            index = find_newline(data, index.saturating_add(2), end)
                .map_or(end, |at| at.saturating_add(1));
        } else if found == Some(Delimiter::Open) {
            let mut depth = 1usize;
            index = index.saturating_add(2);
            while index < end && depth > 0 {
                index = index.saturating_add(nested_step(delimiter(data, index), &mut depth));
            }
        } else {
            break;
        }
    }
    index
}

/// `_string_end`: the end of the string token at `index`. Python never skips an escape here.
fn string_end(data: &[u8], mut index: usize, end: usize) -> Option<usize> {
    if is_raw_mark(byte(data, index)) && is_quote(byte(data, index.saturating_add(1))) {
        index = index.saturating_add(1);
    }
    let quote = quote_at(data, index)?;
    let mut cursor = index.saturating_add(quote.len());
    while cursor < end {
        if starts_with(data, &quote, cursor) {
            return Some(cursor.saturating_add(quote.len()));
        }
        cursor = cursor.saturating_add(1);
    }
    None
}

/// `_string_sequence`: the decoded text of adjacent string literals, `None` when one does not
/// decode, and `None` when no literal starts after the trivia.
pub(crate) fn string_sequence(data: &[u8], start: usize, end: usize) -> Option<String> {
    let mut index = skip_trivia(data, start, end);
    let mut pieces: Vec<String> = Vec::new();
    while index < end {
        let Some(token_end) = string_end(data, index, end) else {
            break;
        };
        let token = data.get(index..token_end.min(data.len())).unwrap_or(b"");
        pieces.push(decode_dart_string(&String::from_utf8_lossy(token))?);
        index = skip_trivia(data, token_end, end);
    }
    (!pieces.is_empty()).then(|| pieces.concat())
}

/// `_directive_uri`: the URI after the keyword `import`, `export` or `part` of a directive.
pub(crate) fn directive_uri(data: &[u8], start: usize, end: usize) -> Option<String> {
    let text = data.get(start..end.min(data.len()))?;
    let keyword = ["import", "export", "part"].into_iter().find(|word| {
        text.starts_with(word.as_bytes())
            && !text.get(word.len()).is_some_and(|next| is_word_byte(*next))
    })?;
    string_sequence(data, start.saturating_add(keyword.len()), end)
}

/// `_decode_dart_string`: the value of one Dart string literal. `None` for interpolation, an
/// unknown escape, a code point above U+10FFFF or a malformed literal. A surrogate code point
/// is also `None`: a Rust string cannot hold it (AD-369).
pub(crate) fn decode_dart_string(raw: &str) -> Option<String> {
    let is_raw = raw.starts_with(['r', 'R']);
    let body = if is_raw { raw.get(1..)? } else { raw };
    let quote = ["'''", "\"\"\"", "'", "\""]
        .into_iter()
        .find(|quote| body.starts_with(quote))?;
    let opening = usize::from(is_raw).saturating_add(quote.len());
    if raw.chars().count() < opening.saturating_add(quote.len()) || !raw.ends_with(quote) {
        return None;
    }
    let content = raw.get(opening..raw.len().saturating_sub(quote.len()))?;
    if is_raw {
        return (!content.contains('$')).then(|| content.to_owned());
    }
    unescape(content).map(Cow::into_owned)
}

/// The escape grammar of `_decode_dart_string` for a string that is not raw.
fn unescape(content: &str) -> Option<Cow<'_, str>> {
    if !content.contains(['\\', '$']) {
        return Some(Cow::Borrowed(content));
    }
    let mut decoded = String::with_capacity(content.len());
    let mut rest = content;
    while let Some(c) = rest.chars().next() {
        if c == '$' {
            return None;
        }
        if c != '\\' {
            let run = rest.find(['\\', '$']).unwrap_or(rest.len());
            decoded.push_str(rest.get(..run)?);
            rest = rest.get(run..)?;
            continue;
        }
        let (value, used) = escape(rest.get(1..)?)?;
        decoded.push(value);
        rest = rest.get(used.saturating_add(1)..)?;
    }
    Some(Cow::Owned(decoded))
}

/// One escape after its backslash: the character and the number of bytes that it uses.
fn escape(text: &str) -> Option<(char, usize)> {
    let first = text.chars().next()?;
    let simple = match first {
        '\\' | '\'' | '"' | '$' => Some(first),
        'n' => Some('\n'),
        'r' => Some('\r'),
        't' => Some('\t'),
        'b' => Some('\u{8}'),
        'f' => Some('\u{c}'),
        'v' => Some('\u{b}'),
        _ => None,
    };
    if let Some(value) = simple {
        return Some((value, 1));
    }
    let digits = |from: usize, count: usize| -> Option<u32> {
        let part = text.get(from..from.saturating_add(count))?;
        if part.len() == count && part.bytes().all(|b| b.is_ascii_hexdigit()) {
            u32::from_str_radix(part, 16).ok()
        } else {
            None
        }
    };
    let (code, used) = match first {
        'x' => (digits(1, 2)?, 3),
        'u' if text.get(1..2) == Some("{") => {
            let count = text
                .get(2..)?
                .bytes()
                .take(7)
                .take_while(u8::is_ascii_hexdigit)
                .count();
            if !(1..=6).contains(&count)
                || text.get(count.saturating_add(2)..count.saturating_add(3)) != Some("}")
            {
                (digits(1, 4)?, 5)
            } else {
                (digits(2, count)?, count.saturating_add(3))
            }
        }
        'u' => (digits(1, 4)?, 5),
        _ => return None,
    };
    if code > 0x0010_FFFF {
        return None;
    }
    Some((char::from_u32(code)?, used))
}

#[cfg(test)]
#[path = "dartstr_tests.rs"]
mod tests;
