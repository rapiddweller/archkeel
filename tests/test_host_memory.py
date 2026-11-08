# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-324: the host writes large JSON in pieces and frees each copy as soon as it is made."""

from archkeel.ir.codec_strings import StringTablePolicy, intern_strings


def test_a_repeated_string_has_one_reference_object() -> None:
    text = "a repeated string that is long enough to be worth a table entry"
    tree, table = intern_strings(
        [[text], [text], [text], [text]], policy=StringTablePolicy.OBSERVATION
    )

    references = [row[0] for row in tree]

    assert table == [text]
    assert references == ["$0"] * 4
    assert len({id(reference) for reference in references}) == 1
