# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validate exact file witnesses in existing nested repository manifests."""

from pathlib import PurePosixPath

from .codec_wire import RawJson, decode_json
from .repository_files import RepositoryFileDigest, repository_file_path


def manifest_file_digests(path: str, content: bytes) -> tuple[tuple[str, str], ...]:
    """Read existing nested path/sha256 registries, rejecting ambiguous or escaping entries."""
    entries: dict[str, str] = {}
    pending: list[RawJson] = [decode_json(content)]
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            if "sha256" in value:
                relative, digest = value.get("path"), value["sha256"]
                if not isinstance(relative, str) or not isinstance(digest, str):
                    raise ValueError("manifest entry requires path and sha256 strings")
                repository_file_path(relative)
                name = (PurePosixPath(path).parent / relative).as_posix()
                repository_file_path(name)
                RepositoryFileDigest(name, digest, "manifest-entry")
                if name in entries:
                    raise ValueError("duplicate manifest file")
                entries[name] = digest
            pending.extend(value.values())
    if not entries:
        raise ValueError("manifest has no file entries")
    return tuple(sorted(entries.items()))
