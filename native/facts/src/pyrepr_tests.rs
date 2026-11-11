// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The expected texts come from CPython 3.11 `repr`.

use super::string;

fn repr(text: &str) -> String {
    let mut out = String::new();
    string(text, &mut out);
    out
}

#[test]
fn a_text_has_the_quotes_and_escapes_of_python_repr() {
    let cases = [
        ("plain", "'plain'"),
        ("it's", "\"it's\""),
        ("say \"hi\"", "'say \"hi\"'"),
        ("both ' and \"", "'both \\' and \"'"),
        ("tab\there\nnl\r", "'tab\\there\\nnl\\r'"),
        ("\u{0}\u{1f}\u{7f}", "'\\x00\\x1f\\x7f'"),
        ("back\\slash", "'back\\\\slash'"),
        ("nbsp\u{a0}x", "'nbsp\\xa0x'"),
        ("zwj\u{200d}x", "'zwj\\u200dx'"),
        ("emoji\u{1F600}", "'emoji\u{1F600}'"),
        ("tag\u{E0001}", "'tag\\U000e0001'"),
        ("\u{fc}\u{20ac}", "'\u{fc}\u{20ac}'"),
        ("\u{2028}", "'\\u2028'"),
    ];
    for (text, expected) in cases {
        assert_eq!(repr(text), expected, "{text:?}");
    }
}

#[test]
fn the_printable_table_is_sorted_and_disjoint() {
    assert_eq!(crate::printable::UNICODE_VERSION, "14.0.0");
    let ranges = super::ranges();
    assert_eq!(
        ranges.len(),
        crate::printable::HIDDEN.split_whitespace().count()
    );
    assert!(ranges
        .windows(2)
        .all(|pair| pair[0].0 <= pair[0].1 && pair[0].1 < pair[1].0));
}
