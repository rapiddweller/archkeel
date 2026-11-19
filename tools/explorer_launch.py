# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Measure repeated Explorer launches against a private disposable cache."""

import json
import os
import select
import signal
import sqlite3
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]


def check_clusters(snapshot: Path, url: str) -> dict[str, str]:
    """Compare one sourced class member per language with the children API."""
    with sqlite3.connect(f"{snapshot.as_uri()}?mode=ro", uri=True) as db:
        coverage = json.loads(db.execute("SELECT coverage FROM analysis").fetchone()[0])
        languages = {part["language"] for part in coverage.get("parts", []) if part.get("language")}
        rows = db.execute(
            "SELECT json_extract(child.body,'$.language'),child.parent,child.id,child.kind "
            "FROM element child JOIN element owner ON child.parent=owner.id "
            "WHERE owner.kind='class' AND child.kind IN ('method','property') "
            "AND json_extract(child.body,'$.source') IS NOT NULL "
            "AND json_extract(owner.body,'$.source') IS NOT NULL ORDER BY child.id"
        )
        examples: dict[str, tuple[str, str, str]] = {}
        for language, owner, child, kind in rows:
            if language and language not in examples:
                examples[language] = (owner, child, kind)
    results = dict.fromkeys(languages, "UNKNOWN: no sourced class member")
    for language, (owner, child, kind) in examples.items():
        cursor = ""
        seen = {cursor}
        while True:
            args = urllib.parse.urlencode({"parent": owner, "limit": 200, "cursor": cursor})
            with urllib.request.urlopen(url + "api/children?" + args, timeout=30) as response:
                payload = json.load(response)
            if any(
                item.get("id") == child and item.get("parent") == owner and item.get("kind") == kind
                for item in payload["items"]
            ):
                results[language] = "PASS"
                break
            cursor = payload.get("next_cursor")
            if cursor is None:
                results[language] = "FAIL: SQL member absent from API"
                break
            if cursor in seen:
                results[language] = "FAIL: API cursor did not advance"
                break
            seen.add(cursor)
    return results


def measure(cli: Path, root: Path, config: str, runs: int = 10) -> dict[str, Any]:
    """Record startup, one bounded query and cache identity for each launch."""
    starts: list[float] = []
    queries: list[float] = []
    snapshots = []
    clusters: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="archkeel-cache-") as cache:
        env = dict(os.environ, XDG_CACHE_HOME=cache)
        for _ in range(runs):
            started = time.monotonic()
            command = [
                str(cli),
                "explore",
                "--root",
                str(root),
                "--config",
                config,
                "--no-open",
                "--json",
            ]
            stderr = tempfile.TemporaryFile(mode="w+t")
            process = subprocess.Popen(
                command,
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
            )
            try:
                assert process.stdout is not None
                ready, _, _ = select.select([process.stdout], [], [], 300)
                if not ready:
                    stderr.seek(0)
                    return {
                        "error": "Explorer startup timed out",
                        "completed": len(starts),
                        "stderr": stderr.read(8192),
                    }
                line = process.stdout.readline()
                try:
                    launch = json.loads(line)
                except ValueError:
                    stderr.seek(0)
                    return {
                        "error": "Explorer startup refused",
                        "completed": len(starts),
                        "stdout": line[:8192],
                        "stderr": stderr.read(8192),
                    }
                if "url" not in launch or "snapshot" not in launch:
                    stderr.seek(0)
                    return {
                        "error": "Explorer did not start",
                        "completed": len(starts),
                        "refusal": launch.get("refusal"),
                        "stderr": stderr.read(8192),
                    }
                starts.append(round(time.monotonic() - started, 4))
                snapshot = Path(launch["snapshot"])
                snapshots.append(
                    (str(snapshot), snapshot.stat().st_mtime_ns, snapshot.stat().st_size)
                )
                started = time.monotonic()
                with urllib.request.urlopen(
                    launch["url"] + "api/children?parent=system", timeout=30
                ) as response:
                    payload = json.load(response)
                if not isinstance(payload.get("items"), list):
                    return {"error": "Explorer query refused", "completed": len(queries)}
                queries.append(round((time.monotonic() - started) * 1000, 3))
                if not clusters:
                    clusters = check_clusters(snapshot, launch["url"])
            except (OSError, ValueError, sqlite3.Error) as error:
                return {"error": type(error).__name__, "completed": len(starts)}
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                stderr.close()
    return {
        "startup_seconds": starts,
        "query_ms": queries,
        "snapshot_bytes": snapshots[0][2],
        "stable_snapshot": len(set(snapshots)) == 1,
        "class_members": clusters,
        "snapshot_versions": [
            {"key": Path(path).stem, "mtime_ns": stamp, "bytes": size}
            for path, stamp, size in snapshots
        ],
        "child_peak_rss": None
        if resource is None
        else resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "rss_note": "cumulative child maximum; platform-specific units",
        "cold_note": "first private cache build; OS page cache not cleared",
        "warm_note": "subsequent launches reuse the same private cache",
    }
