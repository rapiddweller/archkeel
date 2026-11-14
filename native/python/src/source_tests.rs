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

#[test]
fn the_text_of_a_line_is_the_part_of_the_python_split() {
    let text = "a \r\nb\rc\n";
    let lines = Lines::new(text);
    let found: Vec<Option<&str>> = (1..=5).map(|line| lines.text(text, line)).collect();
    assert_eq!(found, [Some("a "), Some("b"), Some("c"), Some(""), None]);
}

#[test]
fn an_encoding_declaration_other_than_utf8_is_refused() {
    for (raw, declared) in [
        (&b"# coding: utf-7\nimport app\n"[..], Some("utf-7")),
        (
            b"#!/usr/bin/env python\n# -*- coding: latin-1 -*-\n",
            Some("latin-1"),
        ),
        (b"# vim: set fileencoding=cp1252 :\n", Some("cp1252")),
        (b"# coding: ascii\nx = '\xc3\xa9'\n", Some("ascii")),
        (b"\xef\xbb\xbf# coding: latin-1\n", Some("latin-1")),
        (b"\xef\xbb\xbf# coding: ascii\n", Some("ascii")),
    ] {
        assert_eq!(declared_encoding(raw).err().as_deref(), declared, "{raw:?}");
    }
}

#[test]
fn a_utf8_or_ascii_declaration_or_none_reads_as_utf8() {
    for raw in [
        &b"# -*- coding: utf-8 -*-\n"[..],
        b"# coding=UTF_8\n",
        b"# coding: utf8\n",
        b"# coding: utf-8-unix\n",
        b"#!/usr/bin/env python\n# coding: utf-8\n",
        b"\xef\xbb\xbf# coding: utf-8\n",
        b"# coding: ascii\nimport app\n",
        b"import app\n# coding: latin-1\n",
        b"x = 1\n",
    ] {
        assert_eq!(declared_encoding(raw), Ok(()), "{raw:?}");
    }
}
