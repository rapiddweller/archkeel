// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `repr()` of a Python `str`, for the text of a record that a Python collector writes with it.
//!
//! The store writes the receipt digest of a dependency proof from it (AD-346), and the native
//! Python collector the message of a shadowed module gap (#797). One implementation serves both.

use std::sync::OnceLock;

use crate::printable::HIDDEN;

/// The ranges of `printable::HIDDEN`, parsed once. A malformed range is skipped; the test of the
/// table checks that every range parses.
fn ranges() -> &'static [(u32, u32)] {
    static RANGES: OnceLock<Vec<(u32, u32)>> = OnceLock::new();
    RANGES.get_or_init(|| {
        HIDDEN
            .split_whitespace()
            .filter_map(|range| {
                let (low, high) = range.split_once('-')?;
                Some((
                    u32::from_str_radix(low, 16).ok()?,
                    u32::from_str_radix(high, 16).ok()?,
                ))
            })
            .collect()
    })
}

fn hidden(point: u32) -> bool {
    ranges()
        .binary_search_by(|&(low, high)| {
            if high < point {
                std::cmp::Ordering::Less
            } else if low > point {
                std::cmp::Ordering::Greater
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

/// The code point from U+0080 on is not printable in Unicode 14.0 (Python 3.11): `repr` escapes
/// it. The native Python collector adds the code points that a later Python prints (AD-377).
pub fn escapes(point: u32) -> bool {
    point >= 0x80 && hidden(point)
}

/// `repr(text)` of CPython: the quote, the escapes and the printable test of `unicode_repr`.
pub fn string(text: &str, out: &mut String) {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    out.push(quote);
    for c in text.chars() {
        let point = u32::from(c);
        match c {
            _ if c == quote || c == '\\' => {
                out.push('\\');
                out.push(c);
            }
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            _ if point < 0x20 || point == 0x7F => out.push_str(&format!("\\x{point:02x}")),
            _ if point < 0x80 || !hidden(point) => out.push(c),
            _ if point <= 0xFF => out.push_str(&format!("\\x{point:02x}")),
            _ if point <= 0xFFFF => out.push_str(&format!("\\u{point:04x}")),
            _ => out.push_str(&format!("\\U{point:08x}")),
        }
    }
    out.push(quote);
}

#[cfg(test)]
#[path = "pyrepr_tests.rs"]
mod tests;
