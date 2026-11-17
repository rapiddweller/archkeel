# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1445: each requirement of the shell contract states its own reason.

Two requirements that share one rationale text hide what each part uses the other part for.
"""

from __future__ import annotations

import json
from collections import Counter

from core_support import ROOT

CONTRACT = "docs/architecture/target/shell-contract.json"


def test_no_two_shell_requirements_share_a_rationale() -> None:
    document = json.loads((ROOT / CONTRACT).read_text())
    rationales = [
        (component["id"], requirement["component"], requirement["rationale"])
        for component in document["components"]
        for requirement in component.get("requires", [])
    ]
    shared = {text: n for text, n in Counter(text for *_, text in rationales).items() if n > 1}
    assert shared == {}, [(owner, target) for owner, target, text in rationales if text in shared]
