// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `repr()` of a Python `str`, for the text of a record that a Python collector writes with it.
//!
//! The store writes the receipt digest of a dependency proof from it (AD-346), and the native
//! Python collector the message of a shadowed module gap (#797). One implementation serves both.

use std::sync::OnceLock;

use crate::printable::HIDDEN;
use crate::pyminor::PyMinor;

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
    in_ranges(point, ranges())
}

fn in_ranges(point: u32, ranges: &[(u32, u32)]) -> bool {
    ranges
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

type Ranges = Vec<(u32, u32)>;
const ADDITIONS: &str = include_str!("pyrepr_printable.txt");

fn additions(minor: PyMinor) -> &'static [(u32, u32)] {
    static TABLES: OnceLock<[Ranges; 3]> = OnceLock::new();
    let tables = TABLES.get_or_init(|| {
        std::array::from_fn(|index| {
            ADDITIONS
                .lines()
                .nth(index)
                .into_iter()
                .flat_map(|line| line.split_whitespace().skip(1))
                .filter_map(|range| {
                    let (low, high) = range.split_once('-')?;
                    Some((
                        u32::from_str_radix(low, 16).ok()?,
                        u32::from_str_radix(high, 16).ok()?,
                    ))
                })
                .collect()
        })
    });
    match minor {
        PyMinor::Py311 => &[],
        PyMinor::Py312 => &tables[0],
        PyMinor::Py313 => &tables[1],
        PyMinor::Py314 => &tables[2],
    }
}

/// `str.isprintable()` in the CPython minor of the request.
pub fn printable(c: char, minor: PyMinor) -> bool {
    let point = u32::from(c);
    if point < 0x20 || point == 0x7f {
        return false;
    }
    if !escapes(point) {
        return true;
    }
    in_ranges(point, additions(minor))
}

/// `repr(text)` of CPython: the quote, the escapes and the printable test of `unicode_repr`.
pub fn string(text: &str, out: &mut String) {
    string_with(text, out, PyMinor::Py311);
}

/// `repr(text)` with the printable table of the decoded CPython minor.
pub fn string_with(text: &str, out: &mut String, minor: PyMinor) {
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
            _ if printable(c, minor) => out.push(c),
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
