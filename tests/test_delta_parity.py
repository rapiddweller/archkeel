# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Golden digests measured against the saved Step 2 checker before the typed port."""

import hashlib

import pytest
from test_delta import _evidence, _model, _record

from archkeel.check.delta import build_architecture_delta
from archkeel.ir.codec import canonical_json_bytes, delta_payload, parse_observation


# AD-43 raised DELTA_SCHEMA_VERSION, so these golden digests moved with the field's own
# byte value; the import records they cover are untouched, so nothing else changed them.
@pytest.mark.parametrize(
    ("before_n", "after_n", "digest"),
    [
        (3, 1, "752a75285e47f32fff5782ff3387531598fbcb6990e95e18f3fc47ecc2a42357"),
        (1, 3, "a26c1656124c0349d409c56c800a16207fbeb5cc66ce457665057a0007febd91"),
        (2, 2, "a7af63bd6f8ef0e91d9505ff4638ffa383755fbb7b82744adc29dca322e29d4f"),
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
