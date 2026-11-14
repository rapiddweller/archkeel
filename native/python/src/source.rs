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

/// The names of UTF-8 that an encoding declaration can give, after lower case and `_` to `-`.
/// CPython also reads each name that starts with `utf-8-` as UTF-8 (`get_normal_name`).
const UTF8: [&str; 5] = ["utf-8", "utf8", "u8", "utf", "cp65001"];
/// The names of ASCII. Such a file must hold only ASCII bytes to read as UTF-8.
const ASCII: [&str; 2] = ["ascii", "us-ascii"];

/// The PEP 263 encoding declaration of a file, checked: `Err` names a declared encoding that the
/// UTF-8 decode cannot read as CPython reads it (AD-450). The declaration is on line 1, or on
/// line 2 when line 1 is blank or only a comment. A byte order mark allows only UTF-8.
pub(crate) fn declared_encoding(raw: &[u8]) -> Result<(), String> {
    let mut lines = raw.split(|byte| *byte == b'\n');
    let first = lines.next().unwrap_or_default();
    let found = match cookie(first) {
        Some(name) => Some(name),
        None if comment_or_blank(first) => lines.next().and_then(cookie),
        None => None,
    };
    let Some(name) = found else {
        return Ok(());
    };
    let normal = name.to_ascii_lowercase().replace('_', "-");
    let utf8 = UTF8.contains(&normal.as_str()) || normal.starts_with("utf-8-");
    let ascii = ASCII.contains(&normal.as_str()) && raw.is_ascii();
    if utf8 || ascii && !raw.starts_with(b"\xef\xbb\xbf") {
        Ok(())
    } else {
        Err(name)
    }
}

/// The encoding name of `#.*?coding[:=][ \t]*([-\w.]+)` on a comment line.
fn cookie(line: &[u8]) -> Option<String> {
    let line = line.strip_prefix(b"\xef\xbb\xbf").unwrap_or(line);
    let start = line
        .iter()
        .position(|byte| !matches!(byte, b' ' | b'\t' | b'\x0c'))?;
    let comment = line[start..].strip_prefix(b"#")?;
    let at = comment
        .windows(7)
        .position(|window| window.starts_with(b"coding") && matches!(window[6], b':' | b'='))?;
    let rest = &comment[at + 7..];
    let rest = &rest[rest
        .iter()
        .take_while(|byte| matches!(byte, b' ' | b'\t'))
        .count()..];
    let name: Vec<u8> = rest
        .iter()
        .copied()
        .take_while(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
        .collect();
    (!name.is_empty()).then(|| String::from_utf8_lossy(&name).into_owned())
}

/// A line of blanks, or blanks and then a comment.
fn comment_or_blank(line: &[u8]) -> bool {
    let line = line.strip_prefix(b"\xef\xbb\xbf").unwrap_or(line);
    let rest: Vec<&u8> = line
        .iter()
        .skip_while(|byte| matches!(byte, b' ' | b'\t' | b'\x0c' | b'\r'))
        .collect();
    rest.first().is_none_or(|byte| **byte == b'#')
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
