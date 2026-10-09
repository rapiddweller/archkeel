# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Select old Actions report artifacts without touching unrelated artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_MANAGED_NAMES = frozenset({"report-browser-evidence", "archkeel-self-observation"})
_RETENTION = timedelta(hours=24)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("artifact timestamp must be a string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("artifact timestamp must be ISO 8601") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("artifact timestamp must include a timezone")
    return result.astimezone(UTC)


def retention_plan(inventory: object, *, now: datetime) -> dict[str, Any]:
    """Keep each newest active managed artifact only while it is under 24 hours old."""
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("expected a non-empty list of paginated artifact responses")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    cutoff = now.astimezone(UTC) - _RETENTION
    seen: dict[int, tuple[str, bool, datetime | None]] = {}
    managed: dict[str, dict[int, datetime]] = {}
    for page in inventory:
        if not isinstance(page, dict) or not isinstance(page.get("artifacts"), list):
            raise ValueError("artifact page artifacts must be a list")
        total_count = page.get("total_count")
        if isinstance(total_count, bool) or not isinstance(total_count, int) or total_count < 0:
            raise ValueError("artifact page total_count must be a nonnegative integer")
        for artifact in page["artifacts"]:
            if not isinstance(artifact, dict):
                raise ValueError("artifact must be an object")
            artifact_id = artifact.get("id")
            name = artifact.get("name")
            expired = artifact.get("expired")
            created_at = artifact.get("created_at")
            if (
                isinstance(artifact_id, bool)
                or not isinstance(artifact_id, int)
                or artifact_id <= 0
            ):
                raise ValueError("artifact id must be a positive integer")
            if not isinstance(name, str) or not isinstance(expired, bool):
                raise ValueError("artifact name and expired state have invalid types")
            timestamp = _timestamp(created_at) if name in _MANAGED_NAMES and not expired else None
            if artifact_id in seen:
                if seen[artifact_id] != (name, expired, timestamp):
                    raise ValueError("duplicate artifact ID has conflicting metadata")
                continue
            seen[artifact_id] = (name, expired, timestamp)
            if timestamp is not None:
                managed.setdefault(name, {})[artifact_id] = timestamp
    keep_ids: set[int] = set()
    for named_artifacts in managed.values():
        recent = [
            (timestamp, artifact_id)
            for artifact_id, timestamp in named_artifacts.items()
            if timestamp >= cutoff
        ]
        if recent:
            keep_ids.add(max(recent)[1])
    delete_ids = sorted(
        artifact_id
        for named_artifacts in managed.values()
        for artifact_id in named_artifacts
        if artifact_id not in keep_ids
    )
    return {
        "observed_count": len(seen),
        "keep_ids": sorted(keep_ids),
        "delete_ids": delete_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path, help="gh api --paginate --slurp JSON")
    parser.add_argument(
        "--output", type=Path, required=True, help="write the validated selection plan"
    )
    args = parser.parse_args()
    try:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        plan = retention_plan(inventory, now=datetime.now(UTC))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "observed_count": plan["observed_count"],
                "keep_count": len(plan["keep_ids"]),
                "delete_count": len(plan["delete_ids"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
