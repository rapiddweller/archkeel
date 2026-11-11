// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn the_decode_drops_one_byte_order_mark_and_refuses_invalid_utf8() {
    assert_eq!(decode(b"\xef\xbb\xbfx = 1\n"), Some("x = 1\n"));
    assert_eq!(
        decode(b"\xef\xbb\xbf\xef\xbb\xbfx"),
        Some("\u{feff}x"),
        "only one mark"
    );
    assert_eq!(decode(b"x = '\xff'\n"), None);
    // A surrogate is not UTF-8 for Python either.
    assert_eq!(decode(b"\xed\xa0\x80"), None);
}

#[test]
fn a_line_ends_at_each_newline_form_of_the_python_split() {
    let lines = Lines::new("a\r\nb\rc\nd");
    let offsets: Vec<usize> = [0, 3, 5, 7].to_vec();
    let found: Vec<usize> = offsets.iter().map(|at| lines.line(*at)).collect();
    assert_eq!(found, [1, 2, 3, 4]);
    assert_eq!(lines.start_of(6), 5);
    assert_eq!(lines.line(1), 1);
}
