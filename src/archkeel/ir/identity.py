# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Collision-free source identities for language-aware import graphs."""

from __future__ import annotations

import re

from .facts import Language


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


def module_identity(namespace: str, repository_relative_path: str, language: Language) -> str:
    """Map a repo-relative path to a module ID; TS IDs preserve every path distinction."""
    parts = _segments(repository_relative_path)
    if language == "typescript":
        if not namespace or any(not part.isidentifier() for part in namespace.split(".")):
            raise ValueError("namespace must be a dotted identifier")
        return ".".join((namespace, *(_typescript_segment(part) for part in parts)))
    if language == "python":
        if parts[-1].endswith(".py"):
            parts = (*parts[:-1], parts[-1][:-3])
        if parts[-1] == "__init__":
            parts = parts[:-1]
        prefix = tuple(namespace.split("."))
        for index in range(len(parts) - len(prefix) + 1):
            if parts[index : index + len(prefix)] == prefix:
                return ".".join(parts[index:])
        raise ValueError(f"source path does not contain configured namespace {namespace!r}")
    if language == "dart":
        if parts[0] == "lib":
            parts = parts[1:]
        if not parts:
            raise ValueError("Dart source path must name a library")
        if parts[-1].endswith(".dart"):
            parts = (*parts[:-1], parts[-1][:-5])
        # The Dart adapter's established URI identity maps dots and hyphens to underscores.
        normalized = tuple(re.sub(r"[.-]", "_", part) for part in parts)
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in normalized):
            raise ValueError("Dart source path cannot be represented as a module identity")
        return ".".join((namespace, *normalized))
    raise ValueError(f"unsupported language: {language}")
