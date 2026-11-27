# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-678: a suppression is a reviewed entry. No `allow` attribute may
enter production Rust code: the reviewed entries of `native/suppressions.json` are the debt that
exists, each with a reason, and the list may only shrink.
"""

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
ALLOW = re.compile(r"#!?\[(?:cfg_attr\([^\]]*?,\s*)?allow\(")


def _suppressions() -> Counter[tuple[str, str]]:
    found: Counter[tuple[str, str]] = Counter()
    for path in sorted((ROOT / "native").rglob("*.rs")):
        relative = path.relative_to(ROOT).as_posix()
        if "/target/" in relative or relative.endswith("_tests.rs") or "/tests/" in relative:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if ALLOW.search(line.strip()):
                found[(relative, line.strip())] += 1
    return found


def test_each_allow_attribute_of_production_rust_is_a_reviewed_entry_with_a_reason() -> None:
    entries = json.loads((ROOT / "native/suppressions.json").read_text(encoding="utf-8"))["entries"]
    listed = Counter((item["path"], item["text"]) for item in entries)
    found = _suppressions()
    assert found - listed == Counter(), "a new allow attribute: fix the code, do not suppress it"
    assert listed - found == Counter(), "an entry of native/suppressions.json that no longer exists"
    assert all(len(item["reason"].strip()) >= 10 for item in entries)


def test_the_suppression_scan_sees_an_allow_and_a_cfg_attr_allow() -> None:
    assert ALLOW.search("#[allow(dead_code)]") and ALLOW.search("#![allow(clippy::x)]")
    assert ALLOW.search('#[cfg_attr(not(feature = "dump"), allow(dead_code))]')
    assert not ALLOW.search('#[expect(dead_code, reason = "x")]')


def test_a_suppression_entry_that_this_branch_adds_carries_a_growth_reason() -> None:
    """AD-733: against origin/main, a new entry needs `growth_reason` (why the debt may grow)."""
    done = subprocess.run(
        ["git", "show", "origin/main:native/suppressions.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        pytest.skip("ratchet: base origin/main unavailable, skipped")
    base = Counter((item["path"], item["text"]) for item in json.loads(done.stdout)["entries"])
    entries = json.loads((ROOT / "native/suppressions.json").read_text(encoding="utf-8"))["entries"]
    new = [item for item in entries if (item["path"], item["text"]) not in base]
    assert [item for item in new if len(str(item.get("growth_reason", "")).strip()) < 10] == [], (
        "a new suppression needs a growth_reason of at least 10 characters"
    )
