# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-406: the Rust corpus through both store doors, and the native workspace by a scan."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
from core_support import NATIVE, NATIVE_SELF_STATUS, SUFFIX, copy_native, ensure_target_dir
from corpus_support import commit_tree, corpus_cases, materialized
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
    assert len(requests) > 50
    print(f"Rust scan corpus: {len(requests)} equal fact sets; {refused} named refusals")


def test_the_core_scans_its_own_workspace_with_no_shell_reply(
    built: Path, tmp_path: Path, frozen_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A facts cache from the environment (the Full job restores one, AD-1212) names its work
    # directory after the path of the manifest, so the copy sits at a path that does not change.
    cache = os.environ.get("ARCHKEEL_FACTS_CACHE")
    root = Path(cache).with_name("own-workspace") if cache else tmp_path / "project"
    shutil.rmtree(root, ignore_errors=True)
    copy_native(root, frozen_root)
    # The frozen copy turns the compiler facts off. `docs/architecture/native.md` draws the edges
    # that the compiler proves (AD-1136), and only a scan with facts observes them: ask for the
    # facts, as the self-check of the gate does (#2127).
    config = root / "native/archkeel.toml"
    config.write_text(
        config.read_text().replace("rust_type_reach = false", "rust_type_reach = true")
    )
    monkeypatch.setenv("ARCHKEEL_ALLOW_BUILD", "1")
    monkeypatch.setenv("ARCHKEEL_FACTS_CACHE", cache or str(tmp_path / "facts"))
    commit_tree(root)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    request = {
        "protocol": native_scan.SCAN_PROTOCOL,
        "root": str(root.resolve()),
        "config": "native/archkeel.toml",
        "git_head": head,
        "dirty": False,
    }
    # No shell collector runs. The only program under test receives the scan identity.
    stdout, code = native_scan.exchange(
        str(built / f"archkeel-core{SUFFIX}"), "scan", json.dumps(request).encode()
    )
    frame = json.loads(stdout)
    # AD-418: the core decides each rule of its own contract, so the frame names no part (exit 0).
    assert code == 0, frame["unsupported"]
    assert not frame["unsupported"]["rules"]
    # AD-1064: the status follows the stated UNKNOWN rules of the self-contract.
    assert frame["status"] == NATIVE_SELF_STATUS[1]
    assert frame["self_test"]["collect"]["request"]["resolver"] == {"language": "rust"}
    assert frame["self_test"]["reply"]["files"] > 200
    assert "producer not verified" not in json.dumps(frame["unsupported"])
