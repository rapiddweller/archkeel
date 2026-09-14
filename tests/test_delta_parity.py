# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Golden digests measured against the saved Step 2 checker before the typed port."""

import hashlib

import pytest
from test_delta import _evidence, _model, _record

from archkeel.check.delta import build_architecture_delta
from archkeel.ir.codec import canonical_json_bytes, delta_payload, parse_observation


@pytest.mark.parametrize(
    ("before_n", "after_n", "digest"),
    [
        (3, 1, "5004bd7aa85becb04a0089e6cb48311e7feec860a7c7cc9b73c19f5fc3c00034"),
        (1, 3, "af5c4b3babfbdda944e026f4ab1dc2609f81cdb7b2cb36d4ab955c8011cc50dc"),
        (2, 2, "6acf0be61a39a951c4101f9660b5cc853c4f00e34826a58ba91bbc6cd9ba3cc2"),
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
