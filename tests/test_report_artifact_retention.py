# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tools.report_artifact_retention import retention_plan

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
ROOT = Path(__file__).parents[1]


def _artifact(
    artifact_id: int,
    name: str,
    created_at: str,
    *,
    expired: bool = False,
) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": name,
        "expired": expired,
        "created_at": created_at,
    }


def _page(*artifacts: dict[str, object], total_count: int | None = None) -> dict[str, object]:
    return {
        "total_count": len(artifacts) if total_count is None else total_count,
        "artifacts": list(artifacts),
    }


def test_retains_only_newest_recent_allowlisted_artifact_across_pages() -> None:
    inventory = [
        _page(
            _artifact(10, "report-browser-evidence", "2026-10-09T11:00:00Z"),
            _artifact(11, "pytest-results", "2026-10-09T11:30:00Z"),
            total_count=4,
        ),
        _page(
            _artifact(12, "report-browser-evidence", "2026-10-09T11:30:00Z"),
            _artifact(13, "archkeel-self-observation", "2026-10-09T10:00:00Z"),
            _artifact(10, "report-browser-evidence", "2026-10-09T11:00:00Z"),
            total_count=5,
        ),
    ]

    plan = retention_plan(inventory, now=NOW)

    assert plan["keep_ids"] == [12, 13]
    assert plan["delete_ids"] == [10]
    assert plan["observed_count"] == 4


def test_deletes_every_managed_artifact_older_than_24_hours() -> None:
    inventory = [
        _page(
            _artifact(20, "archkeel-self-observation", "2026-10-08T11:59:59Z"),
            _artifact(21, "report-browser-evidence", "2026-10-08T12:00:00Z"),
            _artifact(22, "report-browser-evidence", "2026-10-08T10:00:00Z"),
        )
    ]

    plan = retention_plan(inventory, now=NOW)

    assert plan["keep_ids"] == [21]
    assert plan["delete_ids"] == [20, 22]


def test_ignores_expired_and_unrelated_artifacts() -> None:
    inventory = [
        _page(
            _artifact(30, "report-browser-evidence", "not-a-timestamp", expired=True),
            _artifact(31, "report-runtime", "not-a-timestamp"),
            _artifact(32, "report-browser-evidence", "2026-10-09T10:00:00Z"),
        )
    ]

    plan = retention_plan(inventory, now=NOW)

    assert plan["keep_ids"] == [32]
    assert plan["delete_ids"] == []


def test_tied_creation_times_keep_highest_numeric_id() -> None:
    inventory = [
        _page(
            _artifact(40, "report-browser-evidence", "2026-10-09T11:00:00Z"),
            _artifact(41, "report-browser-evidence", "2026-10-09T11:00:00Z"),
        )
    ]

    plan = retention_plan(inventory, now=NOW)

    assert plan["keep_ids"] == [41]
    assert plan["delete_ids"] == [40]


def test_empty_inventory_has_no_deletions() -> None:
    assert retention_plan([_page()], now=NOW)["delete_ids"] == []


@pytest.mark.parametrize("delete", [False, True])
def test_make_prune_target_writes_plan_before_optional_deletion(
    tmp_path: Path, delete: bool
) -> None:
    now = datetime.now(UTC)
    earlier = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    latest = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    inventory = [
        {
            "total_count": 2,
            "artifacts": [
                _artifact(60, "report-browser-evidence", earlier),
                _artifact(61, "report-browser-evidence", latest),
            ],
        }
    ]
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory))
    calls_path = tmp_path / "gh-calls.jsonl"
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['MOCK_GH_CALLS'], 'a') as calls:\n"
        "    calls.write(json.dumps(args) + '\\n')\n"
        "if '--method' in args:\n"
        "    plan = json.loads(pathlib.Path(os.environ['EXPECTED_PLAN']).read_text())\n"
        "    assert plan['delete_ids'] == [60]\n"
        "else:\n"
        "    print(pathlib.Path(os.environ['MOCK_GH_INVENTORY']).read_text())\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    plan_dir = tmp_path / "plan"
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "prune-report-artifacts",
            f"DELETE={str(delete).lower()}",
            f"REPORT_ARTIFACT_PRUNE_DIR={plan_dir}",
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "GITHUB_REPOSITORY": "example/project",
            "MOCK_GH_CALLS": str(calls_path),
            "MOCK_GH_INVENTORY": str(inventory_path),
            "EXPECTED_PLAN": str(plan_dir / "plan.json"),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads((plan_dir / "plan.json").read_text())["delete_ids"] == [60]
    calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
    assert calls[0] == [
        "api",
        "--paginate",
        "--slurp",
        "repos/example/project/actions/artifacts?per_page=100",
    ]
    assert calls[1:] == (
        [["api", "--method", "DELETE", "repos/example/project/actions/artifacts/60"]]
        if delete
        else []
    )


@pytest.mark.parametrize(
    "inventory",
    [
        [],
        [{}],
        [{"artifacts": []}],
        [{"total_count": -1, "artifacts": []}],
        [{"total_count": True, "artifacts": []}],
        [{"total_count": "1", "artifacts": []}],
        [{"total_count": 1.0, "artifacts": []}],
        [_page(_artifact(52, "report-browser-evidence", "not-a-timestamp"))],
        [
            _page(
                _artifact(53, "report-browser-evidence", "2026-10-09T11:00:00Z"),
                _artifact(53, "report-browser-evidence", "2026-10-09T10:00:00Z"),
            )
        ],
    ],
)
def test_malformed_or_incomplete_inventory_fails_closed(
    inventory: list[dict[str, object]],
) -> None:
    with pytest.raises(ValueError):
        retention_plan(inventory, now=NOW)
