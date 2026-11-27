# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-406: the Rust corpus through both store doors, and the native workspace by a scan."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from core_support import (
    NATIVE,
    SUFFIX,
    ensure_target_dir,
)
from corpus_support import corpus_cases, materialized
from filelock import FileLock
from frozen_native import frozen_root as frozen_root

from archkeel.cli import native_scan


def _derived(core: Path, root: Path, config: str) -> dict[str, Any]:
    """What the core says about the collection of `root`: its request, or its refusal."""
    request = {"protocol": native_scan.SCAN_PROTOCOL, "root": str(root), "config": config}
    stdout, _ = native_scan.exchange(str(core), "scan", json.dumps(request).encode())
    collect: dict[str, Any] = json.loads(stdout)["self_test"]["collect"]
    return collect


def test_each_rust_corpus_request_has_equal_facts_or_a_named_refusal(
    built: Path, tmp_path: Path, frozen_root: Path
) -> None:
    """The core derives the request of each Rust case. The Rust test then reads the facts of that
    request through both doors of the store and finds no difference."""
    core = built / f"archkeel-core{SUFFIX}"
    requests: list[tuple[str, Any]] = []
    refused = 0
    with contextlib.ExitStack() as stack:
        for case in corpus_cases():
            root = stack.enter_context(materialized(case)).resolve()
            try:
                scan = tomllib.loads((root / "archkeel.toml").read_text())["scan"]
            except (OSError, KeyError, tomllib.TOMLDecodeError):
                continue
            if scan.get("language") != "rust":
                continue
            collect = _derived(core, root, "archkeel.toml")
            if "request" in collect:
                requests.append((case.id, collect["request"]))
            else:
                assert collect["refused"].startswith("collect: unsupported: "), (case.id, collect)
                refused += 1
        # A frozen copy: a build in `native/target` of this checkout must not change the scan.
        current = _derived(core, frozen_root, "native/archkeel.toml")["request"]
        requests.append(("current-native", current))
        manifest = tmp_path / "requests.json"
        manifest.write_text(json.dumps(requests))
        command = ["cargo", "test", "--locked", "-p", "archkeel-collect", "--lib"]
        command += ["the_rust_corpus_uses_byte_equal_facts", "--", "--nocapture"]
        ensure_target_dir(NATIVE)
        # The build lock of all workers: cargo must not build in the shared target at the same time.
        with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
            done = subprocess.run(
                command,
                cwd=NATIVE,
                env={
                    **os.environ,
                    "CARGO_TARGET_DIR": str(NATIVE / "target" / "shell"),
                    "ARCHKEEL_COLLECT_RUST_REQUESTS": str(manifest),
                },
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        assert done.returncode == 0, done.stdout + done.stderr
    assert f"Rust fact parity: {len(requests)} equal; 0 differences" in done.stderr
    assert requests, "the scan corpus is empty"
    print(f"Rust scan corpus: {len(requests)} equal fact sets; {refused} named refusals")
