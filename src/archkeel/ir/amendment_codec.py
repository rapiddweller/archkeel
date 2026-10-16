# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read and write amendment artifacts without deciding whether they authorize a change."""

from __future__ import annotations

import json
import re

from .amendment import Amendment, AmendmentVersion
from .codec_wire import _exact, _nonempty, _object, _string
from .model import RawJson as RawJson


def _amendment_digest(raw: RawJson, label: str) -> str:
    value = _string(raw, label)
    if re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def parse_amendment(raw: object) -> Amendment:
    document = _object(raw, "amendment")
    raw_version = document.get("schema_version")
    try:
        version = AmendmentVersion(raw_version)
    except (TypeError, ValueError) as error:
        raise ValueError(f"unsupported amendment schema {raw_version!r}") from error
    fields = {"schema_version", "before_digest", "after_digest", "decided_by", "rationale"}
    if version == AmendmentVersion.V2:
        fields |= {"before_baseline_digest", "after_baseline_digest"}
    document = _exact(raw, fields, "amendment")
    before_baseline = document.get("before_baseline_digest")
    after_baseline = document.get("after_baseline_digest")
    return Amendment(
        _amendment_digest(document["before_digest"], "amendment.before_digest"),
        _amendment_digest(document["after_digest"], "amendment.after_digest"),
        _nonempty(document["decided_by"], "amendment.decided_by"),
        _nonempty(document["rationale"], "amendment.rationale"),
        None
        if before_baseline is None
        else _amendment_digest(before_baseline, "amendment.before_baseline_digest"),
        None
        if after_baseline is None
        else _amendment_digest(after_baseline, "amendment.after_baseline_digest"),
        version,
    )


def amendment_bytes(amendment: Amendment) -> bytes:
    """Write the amendment indented and sorted: this file is read and reviewed in diffs."""
    payload: dict[str, RawJson] = {
        "schema_version": amendment.schema_version,
        "before_digest": amendment.before_digest,
        "after_digest": amendment.after_digest,
        "decided_by": amendment.decided_by,
        "rationale": amendment.rationale,
    }
    if amendment.schema_version == AmendmentVersion.V2:
        payload["before_baseline_digest"] = amendment.before_baseline_digest
        payload["after_baseline_digest"] = amendment.after_baseline_digest
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
