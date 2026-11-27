# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1211: the cache of pinned sources is marked, so a scan of the repository skips it."""

from __future__ import annotations

from pathlib import Path

from tools.fixture_source import CACHE_TAG, mark_cache


def test_the_cache_folder_gets_one_cachedir_tag(tmp_path: Path) -> None:
    cache = tmp_path / "test-artifacts" / "source-cache"
    mark_cache(cache)
    mark_cache(cache)
    assert (cache / "CACHEDIR.TAG").read_text(encoding="utf-8") == CACHE_TAG
    assert CACHE_TAG.startswith("Signature: 8a477f597d28d172789f06886806bc55")
