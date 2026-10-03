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
# digests move with the canonical payload, including the official analyzer identity.
@pytest.mark.parametrize(
    ("before_n", "after_n", "digest"),
    [
        (3, 1, "a08315203a38cdb703ab42f7ece3d1a96afa1593ce8967728706290c397ca20f"),
        (1, 3, "9fdd8f01ce396c67cccecc1ab3fa06456fb69ea766367381048e1f9ead222a3c"),
        (2, 2, "9acee0f124c1584391a4d49d9ee289a3d2614cc583205698d979cbb8258d72b2"),
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
