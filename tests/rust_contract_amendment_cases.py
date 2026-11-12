# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-375: the amendment bytes of the parity test of the Rust amendment codec.

A case is a name and the bytes of one amendment file. The cases come from one changed field of a
valid amendment (each type, each digest form, each blank text, each schema version), from schema
1.0.0, and from hand-written hostile bytes.
"""

from __future__ import annotations

import json
from typing import Any

DIGEST = "0123456789abcdef" * 4
OTHER = "f" * 64
KEYS = (
    "schema_version",
    "before_digest",
    "after_digest",
    "decided_by",
    "rationale",
    "before_baseline_digest",
    "after_baseline_digest",
)
DIGESTS = ("before_digest", "after_digest", "before_baseline_digest", "after_baseline_digest")
TEXTS = ("decided_by", "rationale")
# Each character of Python `str.isspace`, and characters that are not white space in Python.
SPACES = "\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0       　"
NOT_SPACES = "​᠎﻿\x00\x7f⁠"
WRONG = (1, None, [], {}, True, 1.5, "x", -1, ["a" * 64], {"a": DIGEST})
SCHEMAS = ("2.0.1", "3.0.0", "", "2.0", "2", " 2.0.0", "2.0.0 ", "2.0.0\x00", "v2", None, 2, 2.0)
TEXT_VALUES = (
    "Jordan (architect)",
    "Ünïcödé — 日本語 😀",
    'a\x01\x1f\x7f  "\\\b\f\n\r\t/',
    "\x00",
    "﻿",
    " x ",
    "'\"'",
)


def document(**changes: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "2.0.0",
        "before_digest": DIGEST,
        "after_digest": OTHER,
        "decided_by": "Jordan",
        "rationale": "Accepted.",
        "before_baseline_digest": None,
        "after_baseline_digest": None,
    }
    value.update(changes)
    return value


def encode(value: object, **options: Any) -> bytes:
    return json.dumps(value, **options).encode("utf-8", "surrogatepass")


def _without(key: str) -> dict[str, Any]:
    value = document()
    del value[key]
    return value


def generated_cases() -> list[tuple[str, bytes]]:
    cases: list[tuple[str, bytes]] = [
        ("valid", encode(document())),
        ("valid indented", encode(document(), indent=2, sort_keys=True) + b"\n"),
        ("valid ascii escapes", encode(document(decided_by="é😀"), ensure_ascii=True)),
        (
            "valid baselines",
            encode(document(before_baseline_digest=DIGEST, after_baseline_digest=OTHER)),
        ),
        ("valid one baseline", encode(document(after_baseline_digest=DIGEST))),
        ("valid other baseline", encode(document(before_baseline_digest=OTHER))),
    ]
    for key in KEYS:
        cases.append((f"missing {key}", encode(_without(key))))
        for wrong in WRONG:
            cases.append((f"wrong {key} {wrong!r}", encode(document(**{key: wrong}))))
    for extra in ("extra", "Decided_by", "", "schema"):
        cases.append((f"unknown field {extra!r}", encode({**document(), extra: "x"})))
    for key in DIGESTS:
        for name, value in (
            ("upper", DIGEST.upper()),
            ("63", DIGEST[:63]),
            ("65", DIGEST + "0"),
            ("g", "g" * 64),
            ("space", DIGEST[:63] + " "),
            ("newline", DIGEST + "\n"),
            ("arabic digits", "٣" * 64),
            ("fullwidth", "ａ" * 64),
            ("empty", ""),
        ):
            cases.append((f"digest {key} {name}", encode(document(**{key: value}))))
    for key in TEXTS:
        cases.append((f"empty {key}", encode(document(**{key: ""}))))
        for space in SPACES:
            cases.append((f"blank {key} {space!r}", encode(document(**{key: space * 2}))))
        cases.append((f"blank {key} all", encode(document(**{key: SPACES}))))
        for text in NOT_SPACES:
            cases.append((f"not blank {key} {text!r}", encode(document(**{key: text}))))
        for text in TEXT_VALUES:
            cases.append((f"text {key} {text!r}", encode(document(**{key: text}))))
    for schema in SCHEMAS:
        cases.append((f"schema {schema!r}", encode(document(schema_version=schema))))
    v1 = {
        key: value
        for key, value in document(schema_version="1.0.0").items()
        if "baseline" not in key
    }
    cases += [
        ("v1 valid", encode(v1)),
        ("v1 with baselines", encode(document(schema_version="1.0.0"))),
        ("v1 bad digest", encode({**v1, "before_digest": "x"})),
        ("v1 blank", encode({**v1, "rationale": " "})),
    ]
    return cases


def _raw(text: str) -> bytes:
    return text.encode("utf-8")


VALID = encode(document())
PREFIX = '{"schema_version": "2.0.0", "before_digest": "%s", "after_digest": "%s", ' % (
    DIGEST,
    OTHER,
)
SUFFIX = ', "before_baseline_digest": null, "after_baseline_digest": null}'


def _with_text(decided_by: str) -> bytes:
    """Raw JSON for `decided_by`, written into the bytes as given (escapes are not added)."""
    return _raw(PREFIX + f'"decided_by": {decided_by}, "rationale": "r"' + SUFFIX)


def hostile_cases() -> list[tuple[str, bytes]]:
    deep = "[" * 100_000 + "]" * 100_000
    many = "{" + ",".join(f'"k{n}": 0' for n in range(1_000_000)) + "}"
    return [
        ("hostile empty", b""),
        ("hostile space", b" "),
        ("hostile null", b"null"),
        ("hostile list", b"[]"),
        ("hostile string", b'"x"'),
        ("hostile number", b"1"),
        ("hostile empty object", b"{}"),
        ("hostile bom", b"\xef\xbb\xbf" + VALID),
        ("hostile utf16", "﻿".encode("utf-16-le") + VALID.decode().encode("utf-16-le")),
        ("hostile trailing text", VALID + b"x"),
        ("hostile trailing object", VALID + b"{}"),
        ("hostile two objects", VALID + VALID),
        ("hostile surrounding space", b"\n\t " + VALID + b"\r\n"),
        ("hostile 10 MB space", b" " * 10_000_000 + VALID),
        ("hostile nan", _with_text("NaN")),
        ("hostile infinity", _with_text("Infinity")),
        ("hostile minus infinity", _with_text("-Infinity")),
        ("hostile big integer", _with_text("1" + "0" * 400)),
        ("hostile big float", _with_text("1e400")),
        ("hostile nested value", _with_text("[" * 1000 + "]" * 1000)),
        ("hostile deep document", _raw(deep)),
        ("hostile deep object", _raw('{"a":' * 5000 + "1" + "}" * 5000)),
        ("hostile 10 MB text", _with_text('"' + "a" * 10_000_000 + '"')),
        ("hostile 10 MB escapes", _with_text('"' + "\\u2028\\n" * 1_000_000 + '"')),
        ("hostile million keys", _raw(many)),
        ("hostile invalid utf8", _with_text('"a') + b"\xff"),
        (
            "hostile invalid utf8 in text",
            _raw(PREFIX + '"decided_by": "a') + b'\xff", "rationale": "r"' + _raw(SUFFIX),
        ),
        (
            "hostile overlong slash",
            _raw(PREFIX + '"decided_by": "') + b"\xc0\xaf" + _raw('", "rationale": "r"' + SUFFIX),
        ),
        (
            "hostile cesu surrogate",
            _raw(PREFIX + '"decided_by": "')
            + b"\xed\xa0\x80"
            + _raw('", "rationale": "r"' + SUFFIX),
        ),
        ("hostile lone high surrogate", _with_text('"\\ud800"')),
        ("hostile lone low surrogate", _with_text('"\\udc00"')),
        ("hostile reversed surrogates", _with_text('"\\udc00\\ud800"')),
        ("hostile surrogate pair", _with_text('"\\ud83d\\ude00"')),
        ("hostile raw control", _with_text('"a\x01b"')),
        ("hostile raw newline", _with_text('"a\nb"')),
        ("hostile raw del", _with_text('"a\x7fb"')),
        ("hostile escaped nul", _with_text('"a\\u0000b"')),
        ("hostile raw line separator", _with_text('"a b"')),
        (
            "hostile escaped key",
            _raw(
                PREFIX.replace('"after_digest"', '"after\\u005fdigest"')
                + '"decided_by": "J", "rationale": "r"'
                + SUFFIX
            ),
        ),
        (
            "hostile duplicate decided_by",
            _raw(PREFIX + '"decided_by": "", "decided_by": "J", "rationale": "r"' + SUFFIX),
        ),
        (
            "hostile duplicate schema",
            _raw(
                '{"schema_version": "1.0.0", '
                + PREFIX[1:]
                + '"decided_by": "J", "rationale": "r"'
                + SUFFIX
            ),
        ),
        (
            "hostile duplicate digest",
            _raw(
                PREFIX + f'"before_digest": "{OTHER}", "decided_by": "J", "rationale": "r"' + SUFFIX
            ),
        ),
        (
            "hostile duplicate nested",
            _raw(PREFIX + '"decided_by": {"a": 1, "a": 2}, "rationale": "r"' + SUFFIX),
        ),
        (
            "hostile duplicate escaped key",
            _raw(PREFIX + '"decided_by": "a", "decided\\u005fby": "b", "rationale": "r"' + SUFFIX),
        ),
        (
            "hostile single quotes",
            _raw(PREFIX + "'decided_by': 'J', \"rationale\": \"r\"" + SUFFIX),
        ),
        (
            "hostile trailing comma",
            _raw(PREFIX + '"decided_by": "J", "rationale": "r",' + SUFFIX[1:]),
        ),
        ("hostile comment", _raw("// c\n") + VALID),
        ("hostile nul byte", b"\x00"),
        ("hostile unquoted key", _raw(PREFIX + 'decided_by: "J", "rationale": "r"' + SUFFIX)),
        ("hostile array of documents", b"[" + VALID + b"]"),
        ("hostile hex escape", _with_text('"\\x41"')),
        ("hostile short unicode escape", _with_text('"\\u41"')),
        ("hostile upper unicode escape", _with_text('"\\u00C9"')),
        ("hostile empty key", _raw(PREFIX + '"": 1, "decided_by": "J", "rationale": "r"' + SUFFIX)),
    ]


def all_cases() -> list[tuple[str, bytes]]:
    return [*generated_cases(), *hostile_cases()]
