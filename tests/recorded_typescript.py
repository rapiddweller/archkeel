# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read public-only Python oracles. A missing key fails by name; native facts never fill it."""

from __future__ import annotations

import hashlib
import json
import os
import zlib
from collections import Counter
from dataclasses import replace
from functools import cache, lru_cache
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from archkeel.ir.facts_codec import decode_response
from archkeel.ir.protocol import CollectionRequest

DIRECTORY = Path(__file__).with_name("typescript_oracle")
COUNTS: Counter[tuple[str, str]] = Counter()


def call_id(test: str) -> str:
    node = test.removesuffix(" (setup)").removesuffix(" (call)").removesuffix(" (teardown)")
    group = "@" + Path(node.split("::", 1)[0]).name
    return "::".join(part.removesuffix(group) for part in node.split("::"))


@cache
def main_calls(directory: Path) -> dict:
    snapshot = json.loads((directory / "manifest.json").read_bytes())
    digest = hashlib.sha256((directory / snapshot["archive"]).read_bytes()).hexdigest()
    assert digest == snapshot["content_digest"], "typescript_oracle_content_digest_mismatch"
    assert len(snapshot["main_sha"]) == 40, "typescript_oracle_main_sha_missing"
    assert all(
        entry["sources"] and set(entry["sources"]) <= {"repository", "excalidraw"}
        for entry in snapshot["tests"].values()
    ), "typescript_oracle_source_outside_public_roots"
    return snapshot


def read(kind: str, *args: object) -> Any:
    test = call_id(os.environ["PYTEST_CURRENT_TEST"])
    index = COUNTS[test, kind]
    COUNTS[test, kind] += 1
    identity = f"{test}::{kind}::{index}"
    if os.environ.get("ARCHKEEL_RECORD_MAIN_WORKTREE"):
        from tools.record_typescript_calls import capture

        data = capture(DIRECTORY, test, kind, args)
    else:
        calls = test_calls(DIRECTORY, test).get(kind, [])
        assert index < len(calls), f"typescript_oracle_missing_key: {identity}"
        saved = calls[index]
        data = saved["text"].encode("utf-8")
        if saved["compressed"]:
            data = zlib.compress(data, level=1)
    return data if kind in {"collect", "locale"} else json.loads(data)


@lru_cache(maxsize=1)
def test_calls(directory: Path, test: str) -> dict:
    snapshot = main_calls(directory)
    entry = snapshot["tests"].get(test)
    assert entry is not None, f"typescript_oracle_missing_key: {test}"
    with ZipFile(directory / snapshot["archive"]) as archive:
        assert entry["file"] in archive.namelist(), f"typescript_oracle_missing_member: {test}"
        data = archive.read(entry["file"])
    assert hashlib.sha256(data).hexdigest() == entry["sha256"], test
    return json.loads(data)


def collect(request: CollectionRequest):  # type: ignore[no-untyped-def]
    facts = decode_response(read("collect", request)).facts
    return replace(
        facts,
        source=replace(
            facts.source, git_head=request.snapshot.git_head, dirty=request.snapshot.dirty
        ),
    )
