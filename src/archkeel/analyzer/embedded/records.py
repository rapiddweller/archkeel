# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Raw record helpers private to the bundled analyzer."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TypeAlias

from archkeel.ir.facts_codec import RawData
from archkeel.ir.facts_codec import (
    RawEvidence as RawEvidence,
)
from archkeel.ir.facts_codec import (
    RawRecord as RawRecord,
)
from archkeel.ir.facts_codec import (
    classified as classified,
)

RecordData: TypeAlias = RawData

ANALYZER_VERSION = "0.64.0"


def analyzer_code_digest() -> str:
    """Hash bundled analyzer source bytes with package-relative framing."""
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        relative = path.name.encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()
