# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-327: the Rust tokenizer and the test-file rule that the two native tools share."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("rust_source", ROOT / "tools/rust_source.py")
assert spec and spec.loader
source = importlib.util.module_from_spec(spec)
sys.modules["rust_source"] = source
spec.loader.exec_module(source)

CASES = [
    ("a lifetime is one name", "fn f<'a>(x: &'a str)", "fn f < 'a > ( x : & 'a str )"),
    ("a quote in a character", "let c = '\"'; let d = 1;", "let c = '\"' ; let d = 1 ;"),
    ("an escaped quote", "let c = '\\''; x", "let c = '\\'' ; x"),
    ("a unicode escape", "let c = '\\u{1F600}'; x", "let c = '\\u{1F600}' ; x"),
    ("a raw string with comment marks", 'r#"// no /* "# x', 'r#"// no /* "# x'),
    ("a raw string with a quote", 'r##"a"#b"## x', 'r##"a"#b"## x'),
    ("a nested block comment", "a /* b /* c */ d */ e", "a e"),
    ("a byte string", 'b"x//y" z', 'b"x//y" z'),
    ("a raw byte string", 'br#"a"# z', 'br#"a"# z'),
    ("doc comments", "/// doc\n//! inner\n/** block */ x", "x"),
    ("a macro variable", "$x:expr", "$ x : expr"),
    ("a range and a float", "1..2 1.5e3", "1 . . 2 1.5e3"),
    ("a string with a comment mark", '"a // b" c', '"a // b" c'),
]


@pytest.mark.parametrize(("label", "text", "expected"), CASES, ids=[case[0] for case in CASES])
def test_tokenizer_cases(label: str, text: str, expected: str) -> None:
    assert " ".join(token.text for token in source.tokenize(text)) == expected


def test_a_lifetime_is_a_name_and_a_character_is_a_literal() -> None:
    kinds = {token.text: token.kind for token in source.tokenize("<'a> 'b' ")}
    assert kinds == {"<": "punct", "'a": "name", ">": "punct", "'b'": "literal"}


def test_lines_survive_comments_and_strings() -> None:
    tokens = source.tokenize('/* one\n/* two */\n*/ a "x\ny" b\n// c\nd')
    assert [(token.text, token.line) for token in tokens] == [
        ("a", 3),
        ('"x\ny"', 3),
        ("b", 4),
        ("d", 6),
    ]


def test_the_test_file_rule() -> None:
    lib = (
        "#[cfg(test)]\nmod checks;\n"
        '#[cfg(test)]\n#[path = "odd_name.rs"]\nmod other;\n'
        '#[cfg(any(test, feature = "x"))]\npub mod helper;\n'
        "mod test_support;\n"
    )
    names = [
        "src/lib.rs",
        "src/checks.rs",
        "src/odd_name.rs",
        "src/helper.rs",
        "src/test_support.rs",
        "src/a_tests.rs",
        "src/tests.rs",
        "tests/x.rs",
        "benches/b.rs",
        "examples/e.rs",
        "src/prod.rs",
    ]
    sources = {name: "" for name in names} | {"src/lib.rs": lib}
    assert source.test_files(sources) == {
        "src/checks.rs",
        "src/odd_name.rs",
        "src/helper.rs",
        "src/a_tests.rs",
        "src/tests.rs",
        "tests/x.rs",
        "benches/b.rs",
        "examples/e.rs",
    }
