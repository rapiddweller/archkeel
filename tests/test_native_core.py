# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-432: the core binary decides, and the shell names it in four modules only.

The tests that compared the core with the Python checker went away with the Python checker. The
tests that stay read the core binary or the native sources and need no Python reference.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import rust_repository
from corpus_support import commit_tree

ROOT = Path(__file__).resolve().parents[1]


def test_a_configured_external_collector_is_refused_and_never_passes(
    tmp_path: Path, core_binary: Path
) -> None:
    """AD-388: the core cannot verify a collector that the project names, so it runs only its
    own. A config with `collector_argv` gives a typed refusal and exit 2, with no rule row."""
    root = rust_repository.repository(tmp_path, core_binary)
    with (root / "archkeel.toml").open("a") as config:
        config.write('collector_argv = ["./collector"]\n')
    commit_tree(root)
    for command in ("validate", "report"):
        code, result = rust_repository.outcome(root, command)
        assert code == 2, result
        assert result["status"] == "UNKNOWN"
        assert not result.get("frame", {}).get("rules")
        message = result["refusal"]["message"]
        assert "the run uses the configured collector ./collector" in message, result


@pytest.mark.parametrize("kind", ["dual-run", "check", "bogus"])
def test_the_release_core_has_no_request_kind_that_carries_a_reply(
    release_core: Path, kind: str
) -> None:
    done = subprocess.run(
        [str(release_core), kind], input=b"{}", capture_output=True, check=False, timeout=60
    )
    assert done.returncode == 2 and done.stdout == b""
    assert b"usage: archkeel-core scan" in done.stderr, done.stderr


def test_a_harness_core_names_itself_in_the_engine_of_its_frame(harness_core: Path) -> None:
    """#1095: the frame of a core that has the reply-carrying request kinds says so after its code
    digest. The request has no reply, so the frame names a gap (exit 3) and still has an engine."""
    request = {
        "protocol": "archkeel-dual-run-5",
        "case": "c",
        "root": "/r",
        "config": "archkeel.toml",
        "baseline": None,
        "collector_argv": None,
        "contracts": {"architecture-contract.json": "{}"},
        "reply": None,
        "sections": [],
        "namespace": "shop",
        "profile": "",
        "standard_library": [],
        "insides": [],
        "roots": [],
    }
    done = subprocess.run(
        [str(harness_core), "dual-run"],
        input=json.dumps(request).encode(),
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert done.returncode == 3, done.stderr
    engine = json.loads(done.stdout)["engine"]
    assert re.fullmatch(r"archkeel-core [0-9a-f]{64}\+harness", engine), engine


def test_the_frozen_copy_holds_the_files_that_native_includes_from_outside() -> None:
    """The copy of native/ must compile: `include_str!` of a file under schema/ needs that file."""
    from frozen_native import live_files

    assert "schema/archkeel-source-suffixes.txt" in live_files()
