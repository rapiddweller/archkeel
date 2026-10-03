# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collision-free TypeScript source identities."""

from __future__ import annotations

import re


def _segments(path: str) -> tuple[str, ...]:
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or "\x00" in path
        or path.startswith("/")
    ):
        raise ValueError("source path must be a safe repository-relative POSIX path")
    parts = tuple(path.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("source path must be a safe repository-relative POSIX path")
    return parts


def _typescript_segment(value: str) -> str:
    encoded = "".join(
        character if re.fullmatch(r"[A-Za-z0-9]", character) else f"_x{ord(character):x}_"
        for character in value
    )
    if encoded[0].isdigit():
        encoded = f"_x{ord(encoded[0]):x}_" + encoded[1:]
    return encoded


def module_identity(namespace: str, repository_relative_path: str) -> str:
    """Encode a TypeScript path as a collision-free module ID."""
    parts = _segments(repository_relative_path)
    if not namespace or any(not part.isidentifier() for part in namespace.split(".")):
        raise ValueError("namespace must be a dotted identifier")
    return ".".join((namespace, *(_typescript_segment(part) for part in parts)))
