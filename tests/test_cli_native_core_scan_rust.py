# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-406: Rust scan decisions, corpus parity and the native workspace without a shell reply."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from test_cli_native_core_scan import (
    NATIVE,
    ROOT,
    SUFFIX,
    _rust_repository,
    _shell_request,
    built,
    core_notes,
    install,
    report,
)

from archkeel.cli import native_scan
from tools.dual_run_corpus import Case, corpus_cases, materialized

__all__ = ["built", "install"]


def test_the_core_decides_a_rust_run_through_the_scan_request(
    install: Path, tmp_path: Path
) -> None:
    root = _rust_repository(install, tmp_path)
    off = report(root)
    code, result = report(root, "--native-core")
    assert (code, result["declared_rules"]) == (off[0], "PASS")
    [note] = core_notes(result)
    assert "The core ran the Rust collector in its own process" in note
    assert result["rule_assessments"] == off[1]["rule_assessments"]


def test_each_rust_corpus_request_has_equal_facts_or_a_named_refusal(
    install: Path, tmp_path: Path
) -> None:
    requests: list[tuple[str, Any]] = []
    accepted = refused = 0
    with contextlib.ExitStack() as stack:
        for case in corpus_cases():
            root = stack.enter_context(materialized(case)).resolve()
            try:
                language = tomllib.loads((root / case.config).read_text())["scan"].get("language")
            except (OSError, KeyError, tomllib.TOMLDecodeError):
                continue
            if language != "rust":
                continue
            payload = _shell_request(root, case)
            requests.append((case.id, json.loads(payload)))
            request = native_scan.scan_request(payload, case.config)
            stdout, _ = native_scan.exchange(
                str(install / f"archkeel-core{SUFFIX}"), "scan", json.dumps(request).encode()
            )
            collect = json.loads(stdout)["self_test"]["collect"]
            if "request" in collect:
                assert native_scan.differences(collect["request"], json.loads(payload)) == [], (
                    case.id
                )
                accepted += 1
            else:
                assert collect["refused"].startswith("collect: unsupported: collector: "), (
                    case.id,
                    collect,
                )
                refused += 1
        current = Case("current-native", "", config="native/archkeel.toml")
        requests.append((current.id, json.loads(_shell_request(ROOT, current))))
        manifest = tmp_path / "requests.json"
        manifest.write_text(json.dumps(requests))
        done = subprocess.run(
            [
                "cargo",
                "test",
                "--locked",
                "-p",
                "archkeel-collect",
                "--lib",
                "the_rust_corpus_uses_byte_equal_facts",
                "--",
                "--nocapture",
            ],
            cwd=NATIVE,
            env={**os.environ, "ARCHKEEL_COLLECT_RUST_REQUESTS": str(manifest)},
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
    assert accepted > 50
    print(
        f"Rust scan corpus: {accepted} accepted; {refused} named refusals; "
        f"{len(requests)} fact comparisons; 0 differences"
    )


def test_the_core_scans_its_own_workspace_with_no_shell_reply(built: Path, tmp_path: Path) -> None:
    from graph_report_support import commit_tree

    root = tmp_path / "project"
    shutil.copytree(NATIVE, root / "native", ignore=shutil.ignore_patterns("target"))
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
    assert frame["status"] in {"FAIL", "UNKNOWN"}
    assert frame["self_test"]["collect"]["request"]["resolver"] == {"language": "rust"}
    assert frame["self_test"]["reply"]["files"] > 200
    assert "producer not verified" not in json.dumps(frame["unsupported"])
