# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Golden digests measured against the saved Step 2 checker before the typed port."""

import hashlib

import pytest
from test_delta import _evidence, _model, _record

from archkeel.check.delta import build_architecture_delta
from archkeel.ir.codec import canonical_json_bytes, delta_payload, parse_observation


# AD-43 raised DELTA_SCHEMA_VERSION, and #88 and #122 each added a measured scalar, so these golden
# digests move with the canonical payload; the import records they cover are untouched.
@pytest.mark.parametrize(
    ("before_n", "after_n", "digest"),
    [
        (3, 1, "f89702ead17067ccc7a6de54c498a664368574798dcc4e47c7f72b0372954403"),
        (1, 3, "c479ce7acf98167eeb55fe31b903795d428970481182da0e93d31483369c55f4"),
        (2, 2, "c6c00b47ef42ee99d812e03de03a430cb491fb31ed7af01c2fe954044af29825"),
    ],
)
def test_typed_delta_preserves_original_canonical_bytes(
    before_n: int, after_n: int, digest: str
) -> None:
    before, after = _model(git_head="a" * 40), _model(git_head="b" * 40)
    for model, count, offset in [(before, before_n, 0), (after, after_n, 5)]:
        model["imports"] = [
            _record(
                f"imp-{index}",
                kind="import",
                evidence_id=f"ev-{index}",
                data={
                    "source_package": "a",
                    "target_package": "b",
                    "source_module": "a.m",
                    "target_module": "b.n",
                    "symbol": "_x",
                },
            )
            for index in range(count)
        ]
        model["evidence"] = [_evidence(f"ev-{index}", index + 1 + offset) for index in range(count)]
    delta = build_architecture_delta(
        parse_observation(before),
        parse_observation(after),
        baseline_digest="c" * 64,
        head_digest="d" * 64,
        checker_digest="e" * 64,
    )
    payload = delta_payload(delta)
    # The new runtime envelope must leave the original semantic bytes unchanged.
    for side in ("baseline", "head"):
        assert payload[side].pop("python_version") == "3.11.12"
    assert hashlib.sha256(canonical_json_bytes(payload)).hexdigest() == digest
