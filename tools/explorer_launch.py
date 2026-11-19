# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Measure repeated Explorer launches against a private disposable cache."""

import json
import os
import select
import signal
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]


def measure(cli: Path, root: Path, config: str, runs: int = 10) -> dict[str, Any]:
    """Record startup, one bounded query and cache identity for each launch."""
    starts: list[float] = []
    queries: list[float] = []
    snapshots = []
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
            process = subprocess.Popen(
                command,
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            try:
                assert process.stdout is not None
                ready, _, _ = select.select([process.stdout], [], [], 300)
                if not ready:
                    return {"error": "Explorer startup timed out", "completed": len(starts)}
                line = process.stdout.readline()
                try:
                    launch = json.loads(line)
                except ValueError:
                    return {"error": "Explorer startup refused", "completed": len(starts)}
                if "url" not in launch or "snapshot" not in launch:
                    return {"error": "Explorer did not start", "completed": len(starts)}
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
            except (OSError, ValueError) as error:
                return {"error": type(error).__name__, "completed": len(starts)}
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    return {
        "startup_seconds": starts,
        "query_ms": queries,
        "snapshot_bytes": snapshots[0][2],
        "stable_snapshot": len(set(snapshots)) == 1,
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
