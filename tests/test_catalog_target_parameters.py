# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Catalog argument: the selected operation must not give away or change its argument (#751)."""

from __future__ import annotations

import pytest
from test_catalog_enum_escape_and_keyword import _argument_rule, _verdicts

CALL = "read_option(OptionKey.PAGE_SIZE)"


def _target_verdict(tmp_path, operation: str, call: str = CALL, rule=None):
    return _verdicts(
        tmp_path,
        caller="from .ops import read_option\nfrom .catalog import OptionKey\n"
        f"def consume():\n    {call}\n",
        rules=[rule or _argument_rule("sample.ops.read_option")],
        extra_files={"sample/ops.py": operation},
    )


# Each target gives the argument to its caller, keeps it, or changes it without a call.
ESCAPING_TARGETS = {
    "return-argument": "def read_option(key):\n    return key\n",
    "return-derived-value": "def read_option(key):\n    return key.__dict__\n",
    "return-container": "def read_option(key):\n    return [key]\n",
    "return-local-alias": "def read_option(key):\n    alias = key\n    return alias\n",
    "return-boolean-fallback": "def read_option(key):\n    return key or 'page_size'\n",
    "store-in-container": "HELD = [None]\ndef read_option(key):\n    HELD[0] = key\n",
    "subscript-store": "def read_option(key):\n    key.__dict__['_value_'] = 'x'\n",
    "subscript-store-keyed-by-argument": "SEEN = {}\ndef read_option(key):\n    SEEN[key] = 1\n",
    "subscript-delete": "def read_option(key):\n    del key.__dict__['_value_']\n",
    "yield": "def read_option(key):\n    yield key\n",
    "await": "async def read_option(key):\n    await key\n",
    "lambda": "def read_option(key):\n    return lambda: key\n",
    "other-formal": "def read_option(key, prefix='p'):\n    return prefix\n",
    # These were UNKNOWN before #751 through a write or a call record. They guard the class.
    "store-in-global": "LAST = None\ndef read_option(key):\n    global LAST\n    LAST = key\n",
    "store-on-object": "class Box:\n    pass\nBOX = Box()\ndef read_option(key):\n"
    "    BOX.last = key\n",
    "attribute-store": "def read_option(key):\n    key._value_ = 'x'\n",
    "pass-on": "def keep(value):\n    return None\ndef read_option(key):\n    return keep(key)\n",
    "nested-function": (
        "def read_option(key):\n    def change():\n        key._value_ = 'x'\n    return change\n"
    ),
    # Strict: these reads cannot change the member, but the flag does not prove it.
    "slice-bound": "TEXT = 'abc'\ndef read_option(key):\n    return TEXT[key:]\n",
    "truth-test": "def read_option(key):\n    return 'set' if key else ''\n",
    "value-read": "def read_option(key):\n    return key.value\n",
}


@pytest.mark.parametrize("form", ESCAPING_TARGETS)
def test_target_that_gives_away_or_changes_an_argument_keeps_argument_unknown(tmp_path, form):
    call = "read_option('page_size', OptionKey.PAGE_SIZE)" if form == "other-formal" else CALL
    assert _target_verdict(tmp_path, ESCAPING_TARGETS[form], call) == ("UNKNOWN", False)


# The two caller shapes of #751: the caller changes the member that the target returns.
@pytest.mark.parametrize(
    "call",
    [
        "read_option(OptionKey.PAGE_SIZE)._value_ = 'x'",
        "member = read_option(OptionKey.PAGE_SIZE)\n    member._value_ = 'x'",
    ],
)
def test_caller_that_changes_the_returned_member_keeps_argument_unknown(tmp_path, call):
    operation = ESCAPING_TARGETS["return-argument"]
    assert _target_verdict(tmp_path, operation, call) == ("UNKNOWN", False)


# A comparison or a subscript index reads the argument but cannot give it away.
CONTAINED_TARGETS = {
    "no-read": "def read_option(key):\n    pass\n",
    "comparison": "def read_option(key):\n    return key == 'page_size'\n",
    "membership": "KNOWN = ('page_size',)\ndef read_option(key):\n    return key in KNOWN\n",
    "subscript-index": "OPTIONS = {'page_size': '25'}\ndef read_option(key):\n"
    "    return OPTIONS[key]\n",
    "index-and-comparison": "OPTIONS = {'page_size': '25'}\ndef read_option(key):\n"
    "    return OPTIONS[key] if key in OPTIONS else ''\n",
}


@pytest.mark.parametrize("form", CONTAINED_TARGETS)
def test_target_that_only_compares_or_indexes_an_argument_still_passes(tmp_path, form):
    assert _target_verdict(tmp_path, CONTAINED_TARGETS[form]) == ("PASS", True)
