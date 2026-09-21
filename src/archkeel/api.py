# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The declared external contract: what a consumer outside this repository may import (AD-64).

`ir.baseline` and `ir.codec` still derive and decode everything a `ViolationRow` needs; this
module adds only the one file read a consumer supplies, the read AD-54 put inside `ir.codec`
by mistake. `__all__` is this module's whole promise: `docs/reference.md`'s "Reading a report's
violations" section documents exactly these three names, and nothing else `ir` exposes.

Every type in that promise is declared with it (AD-70). A facade that returned `Observation`
would promise `ir`'s whole model to a consumer while claiming `ir` stays free to change, which
is the leak `boundary_types` reports inside this repository.
"""

from __future__ import annotations

from pathlib import Path

from archkeel.ir.baseline import ViolationFingerprint, ViolationRow, violation_rows
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_observation

__all__ = ["ViolationFingerprint", "ViolationRow", "load_violations"]


def load_violations(path: Path) -> tuple[ViolationRow, ...]:
    """Read one `architecture.json` report from disk and return its violations (AD-70).

    One call, because the two it replaces only ever composed: the `Observation` between them
    was `ir`'s own model crossing a boundary this module exists to keep stable. `decode_json`,
    `decode_canonical_model`, `parse_observation` and `violation_rows` are the internal steps a
    consumer would otherwise compose against a columnar, string-interned file format. `ir`
    itself performs no I/O (AD-17); the read belongs here, at the boundary a consumer crosses.
    """
    raw = decode_json(path.read_bytes())
    if not isinstance(raw, dict):
        raise ValueError("architecture.json must be an object")
    return violation_rows(parse_observation(decode_canonical_model(raw)))
