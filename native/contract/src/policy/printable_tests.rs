// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The printable table of Python 3.11 (L-28): its digest and the code points that the review of
//! #1060 named.

use sha2::{Digest, Sha256};

use crate::policy::printable::NOT_PRINTABLE;
use crate::policy::reference::{printable, python_repr};

#[test]
fn the_table_is_the_table_of_python_3_11() {
    let text: String = NOT_PRINTABLE
        .iter()
        .map(|(start, end)| format!("{start:x}-{end:x}\n"))
        .collect();
    let digest: String = Sha256::digest(text.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    assert_eq!(NOT_PRINTABLE.len(), 701);
    assert_eq!(
        digest,
        "13fcd86f3a19d26a9a02b3962f9c136d5921f698671e37dd673f72507feb9e02"
    );
}

#[test]
fn the_named_code_points_are_escaped_as_python_escapes_them() {
    let cases = [
        ('\u{AD}', "'\\xad'"),
        ('\u{200B}', "'\\u200b'"),
        ('\u{2028}', "'\\u2028'"),
        ('\u{202E}', "'\\u202e'"),
        ('\u{3000}', "'\\u3000'"),
        ('\u{E000}', "'\\ue000'"),
        ('\u{FEFF}', "'\\ufeff'"),
        ('\u{E0001}', "'\\U000e0001'"),
        ('\u{378}', "'\\u0378'"),
        ('\u{1FAE8}', "'\\U0001fae8'"),
    ];
    for (character, expected) in cases {
        assert!(!printable(character), "{character:?}");
        assert_eq!(python_repr(&character.to_string()), expected);
    }
}

#[test]
fn a_printable_character_stays() {
    for character in [' ', 'é', 'ß', '\u{1F600}', '\u{301}', '中'] {
        assert!(printable(character), "{character:?}");
        assert_eq!(
            python_repr(&character.to_string()),
            format!("'{character}'")
        );
    }
}
