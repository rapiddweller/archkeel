# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Current delta retains both accepted legacy Python byte contracts."""

import hashlib

import pytest
from test_delta import _evidence, _model, _record

from archkeel.check.delta import build_architecture_delta
from archkeel.ir.codec import canonical_json_bytes, delta_payload, parse_observation


# Normalize only the format version to check both frozen legacy byte contracts.
@pytest.mark.parametrize(
    ("before_n", "after_n", "parent_digest", "digest"),
    [
        (
            3,
            1,
            "a08315203a38cdb703ab42f7ece3d1a96afa1593ce8967728706290c397ca20f",
            "c881f3bf17e6f13a8594ff06f74cd7212e9d0dfab199dd595a9e0a2771e96ed6",
        ),
        (
            1,
            3,
            "9fdd8f01ce396c67cccecc1ab3fa06456fb69ea766367381048e1f9ead222a3c",
            "1c4a3100617c9f1aa63d61b2ca41870bb1a346826d9c952e0d5ebe5ac343640f",
        ),
        (
            2,
            2,
            "9acee0f124c1584391a4d49d9ee289a3d2614cc583205698d979cbb8258d72b2",
            "c51c7035ce2ca498c0572fae40c767a7b53d380773f61f35acf9b51f48ffe414",
        ),
    ],
)
def test_current_delta_canonical_bytes_preserve_legacy_python_semantics(
    before_n: int, after_n: int, parent_digest: str, digest: str
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
    for side in ("baseline", "head"):
        assert payload[side].pop("python_version") == "3.11.12"
        assert payload["ratchets"][side]["scalars"]["typing_positions"] == 0
    assert payload["schema_version"] == "2.0.0"
    for dimension in payload["dimensions"].values():
        assert dimension["status"] == "SUPPORTED"
        assert dimension["before_count"] is not None
        assert dimension["after_count"] is not None
    payload["schema_version"] = "1.4.0"
    assert hashlib.sha256(canonical_json_bytes(payload)).hexdigest() == digest
    payload["schema_version"] = "1.3.0"
    assert hashlib.sha256(canonical_json_bytes(payload)).hexdigest() == parent_digest
