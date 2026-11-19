# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Record bounded report topology for a local corpus without publishing it."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

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
    "platform": ("src/alembic/env.py", "from alembic import context", "src.alembic.env", "alembic"),
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


def run(name: str, root: Path, config: str | None, output: Path, cli: Path) -> dict[str, Any]:
    if not root.is_dir():
        return {"name": name, "error": "repository unavailable"}
    if config is None and not (root / "archkeel.toml").is_file():
        return run_copy(name, root, output, cli)
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
        if edge.get("source") == source
        and any(
            site.get("path") == path and site.get("line") == line
            for site in edge.get("evidence", [])
        )
    ]
    found = any(edge.get("target") == target for edge in anchored)
    wrong = any(edge.get("target") != target for edge in anchored)
    # A bounded topology cannot prove a missing edge or a negative import.
    return {
        "positive_import": "observed" if found else "not observed",
        "negative_import": "wrong edge observed" if wrong else "UNKNOWN",
    }


def run_copy(name: str, root: Path, output: Path, cli: Path) -> dict[str, Any]:
    """Let the CLI draft a config in a disposable copy, never in the source tree."""
    files = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
        capture_output=True,
        check=False,
    )
    if files.returncode:
        return {"name": name, "error": "cannot list repository files"}
    with tempfile.TemporaryDirectory(prefix="archkeel-corpus-") as directory:
        copy = Path(directory)
        for raw in files.stdout.split(b"\0"):
            if not raw:
                continue
            relative = Path(raw.decode())
            source = root / relative
            if source.is_symlink():
                continue
            if source.is_file():
                target = copy / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        subprocess.run(["git", "init", "-q", str(copy)], check=True)
        result = (
            run(name, copy, None, output, cli)
            if (copy / "archkeel.toml").exists()
            else scan_copy(name, copy, output, cli)
        )
    dirty = git(root, "status", "--porcelain")
    result["head"] = git(root, "rev-parse", "HEAD")
    result["dirty"] = None if dirty is None else bool(dirty)
    result["disposable_copy"] = True
    return result


def scan_copy(name: str, root: Path, output: Path, cli: Path) -> dict[str, Any]:
    """Initialize a draft in the copy, then scan it if initialization succeeds."""
    result = subprocess.run(
        [str(cli), "init", "--root", str(root)],
        cwd=root,
        capture_output=True,
        check=False,
        timeout=300,
    )
    if result.returncode:
        return {"name": name, "error": "draft initialization failed", "exit": result.returncode}
    config = "archkeel.toml"
    if not (root / config).exists():
        config = "docs/architecture/architecture-system.json"
    if not (root / config).exists():
        return {"name": name, "error": "draft did not create a configuration"}
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Corpus",
            "-c",
            "user.email=corpus@example.invalid",
            "commit",
            "-qm",
            "Snapshot",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return run(name, root, config, output, cli)


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
        or "error" in (result.get("launch") or {})
        or not (result.get("launch") or {}).get("stable_snapshot", False)
    )


if __name__ == "__main__":
    raise SystemExit(main())
