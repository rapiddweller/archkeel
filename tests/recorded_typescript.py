# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the last live Python oracle. Missing recordings fail; native output never fills them."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections import Counter
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from archkeel.ir.facts_codec import decode_response
from archkeel.ir.protocol import CollectionRequest

DIRECTORY = Path(__file__).with_name("typescript_oracle")
COUNTS: Counter[tuple[str, str]] = Counter()


def call_id(test: str) -> str:
    """xdist's file group is scheduling metadata, not part of the recorded test identity."""
    node = test.rsplit(" (", 1)[0]
    group = "@" + Path(node.split("::", 1)[0]).name
    return "::".join(part.removesuffix(group) for part in node.split("::"))


@cache
def main_calls(directory: Path) -> dict:
    header = directory / "main-calls.json"
    if not header.is_file():
        return {}
    snapshot = json.loads(header.read_bytes())
    digest = hashlib.sha256((directory / snapshot["archive"]).read_bytes()).hexdigest()
    assert digest == snapshot["content_digest"], "typescript_oracle_content_digest_mismatch"
    return snapshot


def read(kind: str, *args: object) -> Any:
    test = call_id(os.environ["PYTEST_CURRENT_TEST"])
    index = COUNTS[test, kind]
    COUNTS[test, kind] += 1
    identity = f"{test}::{kind}::{index}"
    name = hashlib.sha256(identity.encode()).hexdigest() + ".bin"
    if kind == "collect" and os.environ.get("ARCHKEEL_RECORD_MAIN_WORKTREE"):
        from tools.record_typescript_calls import capture

        return capture(DIRECTORY, identity, args[0])
    if os.environ.get("ARCHKEEL_RECORD_TYPESCRIPT") == "1":
        from tools.record_typescript_oracle import capture

        return capture(DIRECTORY, name, identity, kind, args)
    manifest = json.loads((DIRECTORY / "manifest.json").read_bytes())
    snapshot = main_calls(DIRECTORY) if kind == "collect" else {}
    entry = snapshot.get("replies", {}).get(identity) or manifest["replies"].get(identity)
    assert entry is not None, f"typescript_oracle_missing_key: {identity}"
    assert entry["file"] == name
    with ZipFile(DIRECTORY / entry.get("archive", snapshot.get("archive"))) as archive:
        assert name in archive.namelist(), f"typescript_oracle_missing_member: {identity}"
        data = archive.read(name)
    assert hashlib.sha256(data).hexdigest() == entry["sha256"], identity
    data = gzip.decompress(data)
    return data if kind in {"collect", "locale"} else json.loads(data)


def collect(request: CollectionRequest):  # type: ignore[no-untyped-def]
    facts = decode_response(read("collect", request)).facts
    return replace(
        facts,
        source=replace(
            facts.source, git_head=request.snapshot.git_head, dirty=request.snapshot.dirty
        ),
    )
