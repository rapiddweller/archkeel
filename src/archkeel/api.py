# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The declared external contract: what a consumer outside this repository may import (AD-64).

`ir.baseline` and `ir.codec` still derive and decode everything a `ViolationRow` needs; this
module adds only the one file read a consumer supplies, the read AD-54 put inside `ir.codec`
by mistake. `__all__` is this module's whole promise: `docs/reference.md`'s "Reading a report's
violations" section documents exactly these three names, and nothing else `ir` exposes.
"""

from __future__ import annotations

from pathlib import Path

from archkeel.ir.baseline import ViolationRow, violation_rows
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_observation
from archkeel.ir.model import Observation

__all__ = ["ViolationRow", "load_observation", "violation_rows"]


def load_observation(path: Path) -> Observation:
    """Read one `architecture.json` report from disk and return its Observation (AD-64).

    The one supported way in: `ir.codec.decode_json`, `decode_canonical_model` and
    `parse_observation` are the internal steps a consumer would otherwise have to compose
    against a columnar, string-interned file format this function is what stays stable across.
    `ir` itself performs no I/O (AD-17); the read belongs here, at the boundary a consumer
    actually crosses.
    """
    raw = decode_json(path.read_bytes())
    if not isinstance(raw, dict):
        raise ValueError("architecture.json must be an object")
    return parse_observation(decode_canonical_model(raw))
