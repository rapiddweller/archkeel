// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A small JSON writer. The driver has no dependency, so it writes the text itself (AD-1047).

use std::fmt::Write;

/// A JSON string with its quotes.
pub(crate) fn text(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// A JSON array of unsigned integers.
pub(crate) fn ids<'a>(it: impl IntoIterator<Item = &'a u32>) -> String {
    let parts: Vec<String> = it.into_iter().map(|n| n.to_string()).collect();
    format!("[{}]", parts.join(","))
}

/// A JSON array of strings.
pub(crate) fn texts<'a>(it: impl IntoIterator<Item = &'a String>) -> String {
    let parts: Vec<String> = it.into_iter().map(|s| text(s)).collect();
    format!("[{}]", parts.join(","))
}
