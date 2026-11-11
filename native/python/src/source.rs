// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The text of one source file: the decode of `decode_source` and the line of a byte offset.

/// `source.decode_source`: strict UTF-8 without one leading byte order mark (#742). `None` is the
/// `UnicodeDecodeError` of Python.
pub fn decode(raw: &[u8]) -> Option<&str> {
    let text = std::str::from_utf8(raw).ok()?;
    Some(text.strip_prefix('\u{feff}').unwrap_or(text))
}

/// The start offset of each line, as `re.split(r"\r\n?|\n", source)` splits the text.
pub struct Lines {
    starts: Vec<usize>,
}

impl Lines {
    pub fn new(text: &str) -> Self {
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
    pub fn line(&self, offset: usize) -> usize {
        self.starts.partition_point(|start| *start <= offset)
    }

    /// The byte offset where the line of `offset` starts.
    pub fn start_of(&self, offset: usize) -> usize {
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
