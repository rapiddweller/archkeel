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
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from archkeel.ir.facts_codec import decode_response
from archkeel.ir.protocol import CollectionRequest

DIRECTORY = Path(__file__).with_name("typescript_oracle")
COUNTS: Counter[tuple[str, str]] = Counter()


def read(kind: str, *args: object) -> Any:
    test = os.environ["PYTEST_CURRENT_TEST"].rsplit(" (", 1)[0]
    index = COUNTS[test, kind]
    COUNTS[test, kind] += 1
    identity = f"{test}::{kind}::{index}"
    name = hashlib.sha256(identity.encode()).hexdigest() + ".bin"
    if os.environ.get("ARCHKEEL_RECORD_TYPESCRIPT") == "1":
        from tools.record_typescript_oracle import capture

        return capture(DIRECTORY, name, identity, kind, args)
    manifest = json.loads((DIRECTORY / "manifest.json").read_bytes())
    entry = manifest["replies"][identity]
    assert entry["file"] == name
    with ZipFile(DIRECTORY / entry["archive"]) as archive:
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
