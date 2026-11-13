# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep every unproved CPython site in a counted condition class."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from python_compile_classes import condition_class

ROOT = Path(__file__).parents[1]
PINS = json.loads((ROOT / "tests/python_compile_messages.json").read_text())
TABLE = json.loads((ROOT / "tests/python_compile_sites.json").read_text())


def test_all_unproved_sites_have_a_counted_class() -> None:
    sites = {site["id"]: site for pin in PINS.values() for site in pin["sites"]}
    counts = Counter(
        condition_class(sites[row["site"]])
        for row in TABLE["rows"]
        if row["status"] == "UNPROVED"
    )
    assert counts == {
        "grammar": 445,
        "resource-allocation": 139,
        "ast-validation": 133,
        "Parser/lexer/lexer.c": 74,
        "Python/compile.c": 55,
        "Parser/pegen_errors.c": 54,
        "Python/symtable.c": 43,
        "Parser/action_helpers.c": 30,
        "Parser/string_parser.c": 29,
        "Parser/pegen.c": 21,
        "Python/codegen.c": 14,
        "Parser/tokenizer.c": 11,
        "Python/flowgraph.c": 11,
        "Parser/tokenizer/helpers.c": 8,
        "Python/ast_opt.c": 6,
        "Parser/tokenizer/file_tokenizer.c": 2,
        "Parser/tokenizer/readline_tokenizer.c": 2,
    }
    assert sum(counts.values()) == TABLE["unproved"] == 1077
