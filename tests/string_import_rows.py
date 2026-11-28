# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The rows of the rules that a contract file holds (AD-1440).

The built-in rule `STRING-IMPORT` is in every Python run but in no contract file.
`tests/test_cli_string_import.py` decides it, so these rows leave it out.
"""

from __future__ import annotations

from typing import Any


def rows(result: dict[str, Any]) -> dict[str, str]:
    found = result["frame"]["rules"].items()
    return {rule: row[1] for rule, row in found if rule != "STRING-IMPORT"}
