# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record bounded report topology for a local corpus without publishing it."""

import argparse
import json
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from archkeel.cli.init_draft import SYSTEM
from archkeel.explorer_queries import query
from tools.explorer_launch import measure

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {
    "archkeel": ("archkeel", "docs/architecture/architecture-system.json"),
    "platform": ("rd-svc-datamimic-platform", None),
    "ee": ("datamimic-ee", None),
    "ce": ("datamimic", None),
    "compass": ("archkeel/fixtures/J-compass", None),
}
ORACLES = {
    "platform": (
        "src/worker/services/migration/db/generate_utils.py",
        "from shared.default.model_generation import BuilderMode",
        "worker.services.migration.db.generate_utils",
        "shared.default.model_generation",
    ),
    "archkeel": (
        "native/build-support/src/lib.rs",
        "use sha2::",
        "native.archkeel_build_support",
        "sha2",
    ),
    "ee": (
        "datamimic_ee/authoring/__init__.py",
        "from datamimic_ee.authoring.adapters.workspace import",
        "datamimic_ee.authoring",
        "datamimic_ee.authoring.adapters.workspace",
    ),
    "ce": (
        "datamimic_ce/authoring/__init__.py",
        "from datamimic_ce.authoring.application.app import",
        "datamimic_ce.authoring",
        "datamimic_ce.authoring.application.app",
    ),
    "compass": (
        "compass_app/app/lib/config/dependencies.dart",
        "import '../data/repositories/activity/activity_repository.dart';",
        "compass.config.dependencies",
        "compass.data.repositories.activity.activity_repository",
    ),
}


def git(root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _query_items(
    snapshot: Path, root: Path, operation: str, args: dict[str, object]
) -> Iterator[dict[str, Any]]:
    cursor = ""
    while True:
        result = query(snapshot, root, operation, args | {"cursor": cursor, "limit": 200})
        items, following = result["items"], result["next_cursor"]
        if not isinstance(items, list) or not isinstance(following, (str, type(None))):
            raise ValueError("invalid Explorer page")
        yield from items
        if following is None:
            return
        if following <= cursor:
            raise ValueError("Explorer cursor did not advance")
        cursor = following


def _observed_import(name: str, root: Path, snapshot: Path) -> dict[str, Any]:
    oracle = ORACLES.get(name)
    if oracle is None:
        return {"error": "no source oracle"}
    path, _, source, _ = oracle
    modules = _query_items(snapshot, root, "search", {"text": source})
    element = next(
        (
            item["id"]
            for item in modules
            if item["kind"] == "module" and item["name"] == source and item.get("path") == path
        ),
        None,
    )
    edges = (
        []
        if element is None
        else list(
            _query_items(
                snapshot,
                root,
                "relations",
                {
                    "element": element,
                    "direction": "out",
                    "kind": "import_site",
                },
            )
        )
    )
    return check_import(name, root, {"edges": edges})


def run(name: str, root: Path, config: str | None, output: Path, cli: Path) -> dict[str, Any]:
    if not root.is_dir():
        return {"name": name, "error": "repository unavailable"}
    if config is None and not (root / "archkeel.toml").is_file() and (root / SYSTEM).is_file():
        config = SYSTEM
    if config is None and not (root / "archkeel.toml").is_file():
        observed_launch = measure(
            cli, root, None, probe=lambda path: _observed_import(name, root, path)
        )
        dirty = git(root, "status", "--porcelain")
        return {
            "name": name,
            "head": git(root, "rev-parse", "HEAD"),
            "dirty": None if dirty is None else bool(dirty),
            "mode": "observed",
            "checks": observed_launch.pop("checks", {}),
            "launch": observed_launch,
        }
    command = [str(cli), "report", "--root", str(root), "--json", "--topology"]
    if config:
        command.extend(["--config", config])
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"name": name, "error": type(error).__name__}
    elapsed = time.monotonic() - started
    path = output / f"{name}.json"
    path.write_bytes(result.stdout)
    try:
        envelope = json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        return {"name": name, "exit": result.returncode, "error": "invalid JSON"}
    topology = (envelope.get("frame") or {}).get("topology")
    dirty = git(root, "status", "--porcelain")
    raw = raw_scan(name, root, config or "archkeel.toml", output)
    launch = measure(cli, root, config or "archkeel.toml") if name in ORACLES else None
    return {
        "name": name,
        "head": git(root, "rev-parse", "HEAD"),
        "dirty": None if dirty is None else bool(dirty),
        "exit": result.returncode,
        "status": envelope.get("status"),
        "refusal": envelope.get("refusal"),
        "seconds": round(elapsed, 3),
        "bytes": len(result.stdout),
        "topology": None
        if topology is None
        else {
            "complete": topology.get("complete"),
            "truncated": topology.get("truncated"),
            "total": topology.get("total"),
            "gaps": topology.get("gaps"),
        },
        "checks": raw,
        "launch": launch,
    }


def _system_part_evidence(
    sections: list[dict[str, Any]], locations: dict[str, Any]
) -> dict[str, Any]:
    expected = {
        "shell": ("python", "src/archkeel/"),
        "core": ("rust", "native/"),
        "studio": ("typescript", "studio/src/"),
    }
    evidence: dict[str, Any] = {}
    for section in sections:
        part = section.get("part")
        if part not in expected:
            continue
        language, path_prefix = expected[part]
        if section.get("language") != language:
            continue
        evidence[part] = next(
            (
                location
                for row in section.get("imports") or []
                for key in row.get("evidence_ids", [])
                if (location := locations.get(key))
                and location["path"].startswith(path_prefix)
                and location["line"] > 0
            ),
            None,
        )
    return {
        "part_evidence": {part: location for part, location in evidence.items() if location},
        "missing_part_evidence": [part for part in expected if not evidence.get(part)],
    }


def raw_scan(name: str, root: Path, config: str, output: Path) -> dict[str, Any]:
    oracle = ORACLES.get(name)
    if oracle is None:
        return {"error": "no source oracle"}
    path, statement, _, target = oracle
    source = root / path
    if not source.is_file() or statement not in source.read_text():
        return {"error": "source oracle changed"}
    line = next(i for i, text in enumerate(source.read_text().splitlines(), 1) if statement in text)
    binary = Path(
        os.environ.get("ARCHKEEL_CORE", str(ROOT / "native/target/release/archkeel-core"))
    )
    request = {
        "protocol": "archkeel-core-scan-1",
        "root": str(root.resolve()),
        "config": config,
        "discover_root": False,
        "topology": True,
        "explorer": True,
    }
    started = time.monotonic()
    try:
        result = subprocess.run(
            [str(binary), "scan"],
            input=json.dumps(request).encode(),
            capture_output=True,
            timeout=300,
            check=False,
        )
        document = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {"error": type(error).__name__}
    (output / f"{name}-raw.json").write_bytes(result.stdout)
    sections = document.get("explorer")
    if not isinstance(sections, list):
        return {"error": "raw explorer data unavailable"}
    locations = document.get("locations", {})
    targets = [
        row.get("target_module")
        for section in sections
        for row in section.get("imports", [])
        if any(
            (locations.get(key, {}).get("path"), locations.get(key, {}).get("line")) == (path, line)
            for key in row.get("evidence_ids", [])
        )
    ]
    return {
        "positive_import": "observed" if target in targets else "missing",
        "wrong_targets": [value for value in targets if value != target],
        "negative_import": "UNKNOWN",
        "collection_gaps": len(document.get("collection_gaps", [])),
        "seconds": round(time.monotonic() - started, 3),
        "bytes": len(result.stdout),
        **(_system_part_evidence(sections, locations) if name == "archkeel" else {}),
    }


def check_import(name: str, root: Path, topology: dict[str, Any] | None) -> dict[str, Any]:
    oracle = ORACLES.get(name)
    if oracle is None or topology is None:
        return {"positive_import": "unavailable", "negative_import": "unavailable"}
    path, statement, source, target = oracle
    file = root / path
    if not file.is_file() or statement not in file.read_text():
        return {"positive_import": "source changed", "negative_import": "unavailable"}
    edges = topology.get("edges", [])
    lines = file.read_text().splitlines()
    line = next(i for i, text in enumerate(lines, 1) if statement in text)
    anchored = [
        edge
        for edge in edges
        if edge.get("source_name", edge.get("source")) == source
        and any(
            site.get("path") == path and site.get("line") == line
            for site in edge.get("evidence", [])
        )
    ]
    found = any(
        edge.get("target_name", edge.get("target")) == target and edge.get("resolution") == "local"
        for edge in anchored
    )
    targets = [edge.get("target_name", edge.get("target")) for edge in anchored]
    wrong = [observed for observed in targets if observed != target]
    # A bounded topology cannot prove a missing edge or a negative import.
    return {
        "positive_import": "observed" if found else "not observed",
        "wrong_targets": wrong,
        "negative_import": "wrong edge observed" if wrong else "UNKNOWN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archkeel-cli", type=Path, default=ROOT / ".venv/bin/archkeel")
    for name in REPOSITORIES:
        parser.add_argument(f"--{name}", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name, (relative, config) in REPOSITORIES.items():
        root = getattr(args, name) or args.workspace / relative
        results.append(run(name, root.resolve(), config, args.output, args.archkeel_cli.resolve()))
        (args.output / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(failed(result) for result in results))


def failed(result: dict[str, Any]) -> bool:
    """Refuse missing or contradictory evidence even when a scan returned a verdict."""
    checks = result.get("checks", {})
    return bool(
        "error" in result
        or result.get("refusal")
        or "error" in checks
        or checks.get("positive_import") != "observed"
        or checks.get("wrong_targets")
        or checks.get("missing_part_evidence")
        or "error" in (result.get("launch") or {})
        or not (result.get("launch") or {}).get("stable_snapshot", False)
        or any(
            value.startswith("FAIL")
            for value in (result.get("launch") or {}).get("class_members", {}).values()
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
