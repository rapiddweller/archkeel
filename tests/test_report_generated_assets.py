# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Report script policies derive from script bytes, not hand-written hashes."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import browser_runtime  # noqa: E402


def pinned_hashes(text: str) -> list[str]:
    """Find SHA-256 base64 values written in Rust source."""
    return re.findall(r'"[A-Za-z0-9+/]{43}="', text)


def test_the_hash_check_detects_a_pinned_sha256() -> None:
    assert pinned_hashes('"EiLkT5U853Rq8jgB5yNwj45vQ2uLN3pqX8dVLzSjB7M="')
    assert not pinned_hashes('env!("ARCHKEEL_ELK_HASH")')


def test_report_policy_does_not_pin_script_hashes() -> None:
    for name in ("html_shell.rs", "html_explorer.rs"):
        text = (ROOT / "native/report/src" / name).read_text()
        assert not pinned_hashes(text), f"{name} pins a script hash"


def test_the_flow_runtime_is_generated_from_its_source() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/browser_runtime.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_a_changed_flow_source_does_not_match_the_committed_runtime() -> None:
    source = browser_runtime.source()
    committed = (browser_runtime.ASSETS / "flow.runtime.js").read_bytes()
    assert browser_runtime.runtime(source + b"\n// changed\n") != committed
