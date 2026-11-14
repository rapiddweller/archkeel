// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The text of one source file: the decode of `decode_source` and the line of a byte offset.

/// `source.decode_source`: strict UTF-8 without one leading byte order mark (#742). `None` is the
/// `UnicodeDecodeError` of Python.
pub(crate) fn decode(raw: &[u8]) -> Option<&str> {
    let text = std::str::from_utf8(raw).ok()?;
    Some(text.strip_prefix('\u{feff}').unwrap_or(text))
}

/// The text that the tokenizer of CPython reads: `ast.parse` of a `str` turns each `\r\n` and
/// each lone `\r` into `\n` before it reads a token (`translate_newlines`), also inside a string
/// literal. A line keeps its number and each column keeps its offset (AD-377).
pub(crate) fn newlines(text: &str) -> std::borrow::Cow<'_, str> {
    if !text.contains('\r') {
        return std::borrow::Cow::Borrowed(text);
    }
    std::borrow::Cow::Owned(text.replace("\r\n", "\n").replace('\r', "\n"))
}

/// The start offset of each line, as `re.split(r"\r\n?|\n", source)` splits the text.
pub(crate) struct Lines {
    starts: Vec<usize>,
}

impl Lines {
    pub(crate) fn new(text: &str) -> Self {
        let bytes = text.as_bytes();
        let mut starts = vec![0];
        let mut at = 0;
        while at < bytes.len() {
            match bytes[at] {
                b'\r' if bytes.get(at + 1) == Some(&b'\n') => {
                    at += 2;
                    starts.push(at);
                }
                b'\r' | b'\n' => {
                    at += 1;
                    starts.push(at);
                }
                _ => at += 1,
            }
        }
        Self { starts }
    }

    /// The 1-based line of a byte offset.
    pub(crate) fn line(&self, offset: usize) -> usize {
        self.starts.partition_point(|start| *start <= offset)
    }

    /// The text of the 1-based `line` without its newline, as the Python split gives it.
    pub(crate) fn text<'t>(&self, text: &'t str, line: usize) -> Option<&'t str> {
        let start = *self.starts.get(line.checked_sub(1)?)?;
        let part = match self.starts.get(line) {
            Some(end) => &text[start..*end],
            None => &text[start..],
        };
        let part = part.strip_suffix('\n').unwrap_or(part);
        Some(part.strip_suffix('\r').unwrap_or(part))
    }

    /// The byte offset where the line of `offset` starts.
    pub(crate) fn start_of(&self, offset: usize) -> usize {
        let line = self.line(offset);
        self.starts
            .get(line.saturating_sub(1))
            .copied()
            .unwrap_or(0)
    }
}

#[cfg(test)]
#[path = "source_tests.rs"]
mod tests;
