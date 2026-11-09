# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""State the examined files in a hand-written reply (AD-344).

A test that builds or changes a reply as JSON calls `stated` after the last change to the files
or the sections. The call writes the statement that a collector writes for an empty checked section.
"""

from __future__ import annotations

from typing import Any

from archkeel.ir.claimed_sections import CHECKED_SECTIONS, examined_digest


def stated(facts: dict[str, Any]) -> dict[str, Any]:
    """Set `capabilities.examined` for each empty checked section of `facts` and return it."""
    digest = examined_digest(file["rel_path"] for file in facts["files"])
    states = {
        section["name"]: digest
        for section in facts["sections"]
        if section["name"] in {item.value for item in CHECKED_SECTIONS} and not section["records"]
    }
    facts["capabilities"].pop("examined", None)
    if states:
        facts["capabilities"]["examined"] = states
    return facts
